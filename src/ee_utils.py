"""Utilitários do Google Earth Engine para o projeto GeoSítio."""

import ee
import geopandas as gpd
import numpy as np
import pandas as pd

from src.config import SITIO_KML


def inicializar_ee(project: str = "adept-primacy-470418-h3"):
    """Inicializa o Earth Engine com o projeto configurado."""
    try:
        ee.Initialize(project=project)
    except Exception:
        ee.Authenticate()
        ee.Initialize(project=project)


def gdf_para_ee_geometry(gdf: gpd.GeoDataFrame) -> ee.Geometry:
    """Converte GeoDataFrame para geometria do Earth Engine (remove Z se houver)."""
    from shapely.ops import transform
    geom_2d = transform(lambda x, y, z=None: (x, y), gdf.geometry.values[0])
    geojson = geom_2d.__geo_interface__
    return ee.Geometry(geojson)


def carregar_geometria_sitio() -> ee.Geometry:
    """Carrega o polígono do sítio como geometria do Earth Engine."""
    gdf = gpd.read_file(SITIO_KML, driver="KML")
    return gdf_para_ee_geometry(gdf)


def coletar_sentinel2(
    geometria: ee.Geometry,
    data_inicio: str,
    data_fim: str,
    max_nuvens: float = 20,
) -> ee.ImageCollection:
    """Coleta imagens Sentinel-2 Surface Reflectance filtradas."""
    return (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(geometria)
        .filterDate(data_inicio, data_fim)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", max_nuvens))
        .sort("CLOUDY_PIXEL_PERCENTAGE")
    )


def adicionar_ndvi(imagem: ee.Image) -> ee.Image:
    """Adiciona banda NDVI a uma imagem Sentinel-2.

    NDVI = (NIR - RED) / (NIR + RED)
    Sentinel-2: NIR = B8, RED = B4
    """
    ndvi = imagem.normalizedDifference(["B8", "B4"]).rename("NDVI")
    return imagem.addBands(ndvi)


def adicionar_indices(imagem: ee.Image) -> ee.Image:
    """Adiciona múltiplos índices espectrais à imagem.

    - NDVI: saúde da vegetação
    - NDWI: presença de água
    - BSI: solo exposto
    """
    ndvi = imagem.normalizedDifference(["B8", "B4"]).rename("NDVI")
    ndwi = imagem.normalizedDifference(["B3", "B8"]).rename("NDWI")

    # Bare Soil Index: ((RED+SWIR) - (NIR+BLUE)) / ((RED+SWIR) + (NIR+BLUE))
    bsi = imagem.expression(
        "((RED + SWIR) - (NIR + BLUE)) / ((RED + SWIR) + (NIR + BLUE))",
        {
            "RED": imagem.select("B4"),
            "SWIR": imagem.select("B11"),
            "NIR": imagem.select("B8"),
            "BLUE": imagem.select("B2"),
        },
    ).rename("BSI")

    return imagem.addBands([ndvi, ndwi, bsi])


def composto_mediana(colecao: ee.ImageCollection, geometria: ee.Geometry) -> ee.Image:
    """Cria um composto de mediana da coleção, recortado pela geometria."""
    return colecao.map(adicionar_indices).median().clip(geometria)


def extrair_serie_temporal_ndvi(
    geometria: ee.Geometry,
    data_inicio: str,
    data_fim: str,
    max_nuvens: float = 30,
) -> pd.DataFrame:
    """Extrai série temporal de NDVI médio dentro da geometria.

    Retorna DataFrame com data e NDVI médio por imagem.
    """
    colecao = coletar_sentinel2(geometria, data_inicio, data_fim, max_nuvens)
    colecao = colecao.map(adicionar_ndvi)

    def extrair_ndvi_medio(imagem):
        stats = imagem.select("NDVI").reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geometria,
            scale=10,
            maxPixels=1e9,
        )
        return imagem.set("ndvi_medio", stats.get("NDVI"))

    colecao_com_stats = colecao.map(extrair_ndvi_medio)

    # Extrair dados
    features = colecao_com_stats.aggregate_array("ndvi_medio").getInfo()
    datas = colecao_com_stats.aggregate_array("system:time_start").getInfo()

    df = pd.DataFrame({
        "data": pd.to_datetime(datas, unit="ms"),
        "ndvi_medio": features,
    })
    df = df.dropna().sort_values("data").reset_index(drop=True)
    return df


def obter_estatisticas_ndvi(imagem: ee.Image, geometria: ee.Geometry) -> dict:
    """Calcula estatísticas NDVI dentro da geometria."""
    stats = imagem.select("NDVI").reduceRegion(
        reducer=ee.Reducer.mean()
        .combine(ee.Reducer.min(), sharedInputs=True)
        .combine(ee.Reducer.max(), sharedInputs=True)
        .combine(ee.Reducer.stdDev(), sharedInputs=True),
        geometry=geometria,
        scale=10,
        maxPixels=1e9,
    )
    resultado = stats.getInfo()
    return {
        "media": resultado.get("NDVI_mean"),
        "minimo": resultado.get("NDVI_min"),
        "maximo": resultado.get("NDVI_max"),
        "desvio_padrao": resultado.get("NDVI_stdDev"),
    }


def gerar_url_tile_ndvi(imagem: ee.Image) -> str:
    """Gera URL de tile do mapa NDVI para sobrepor no Folium.

    Paleta: vermelho (solo exposto) → amarelo → verde escuro (vegetação saudável)
    """
    vis_params = {
        "bands": ["NDVI"],
        "min": -0.2,
        "max": 0.8,
        "palette": [
            "#d73027",  # vermelho — solo exposto / sem vegetação
            "#f46d43",  # laranja
            "#fdae61",  # laranja claro
            "#fee08b",  # amarelo
            "#d9ef8b",  # verde claro
            "#a6d96a",  # verde
            "#66bd63",  # verde médio
            "#1a9850",  # verde escuro — vegetação densa e saudável
        ],
    }
    map_id = imagem.getMapId(vis_params)
    return map_id["tile_fetcher"].url_format


def gerar_url_tile_rgb(imagem: ee.Image) -> str:
    """Gera URL de tile da imagem em cor verdadeira (RGB)."""
    vis_params = {
        "bands": ["B4", "B3", "B2"],
        "min": 0,
        "max": 3000,
        "gamma": 1.3,
    }
    map_id = imagem.getMapId(vis_params)
    return map_id["tile_fetcher"].url_format


# ============================================================
# Elevação e Relevo (SRTM)
# ============================================================

def carregar_elevacao(geometria: ee.Geometry) -> ee.Image:
    """Carrega dados SRTM 30m recortados pela geometria."""
    srtm = ee.Image("USGS/SRTMGL1_003")
    return srtm.clip(geometria)


def calcular_declividade(elevacao: ee.Image) -> ee.Image:
    """Calcula declividade (slope) em graus a partir do MDE."""
    return ee.Terrain.slope(elevacao).rename("declividade")


def calcular_aspecto(elevacao: ee.Image) -> ee.Image:
    """Calcula aspecto (orientação da encosta) em graus a partir do MDE."""
    return ee.Terrain.aspect(elevacao).rename("aspecto")


def calcular_hillshade(elevacao: ee.Image, azimute: float = 315, zenite: float = 35) -> ee.Image:
    """Calcula sombreamento do relevo (hillshade) para visualização 3D."""
    return ee.Terrain.hillshade(elevacao, azimute, zenite).rename("hillshade")


def obter_estatisticas_elevacao(elevacao: ee.Image, geometria: ee.Geometry) -> dict:
    """Calcula estatísticas de elevação dentro da geometria."""
    stats = elevacao.select("elevation").reduceRegion(
        reducer=ee.Reducer.mean()
        .combine(ee.Reducer.min(), sharedInputs=True)
        .combine(ee.Reducer.max(), sharedInputs=True)
        .combine(ee.Reducer.stdDev(), sharedInputs=True),
        geometry=geometria,
        scale=30,
        maxPixels=1e9,
    )
    resultado = stats.getInfo()
    return {
        "media": resultado.get("elevation_mean"),
        "minimo": resultado.get("elevation_min"),
        "maximo": resultado.get("elevation_max"),
        "desvio_padrao": resultado.get("elevation_stdDev"),
        "desnivel": resultado.get("elevation_max") - resultado.get("elevation_min"),
    }


def obter_estatisticas_declividade(declividade: ee.Image, geometria: ee.Geometry) -> dict:
    """Calcula estatísticas de declividade dentro da geometria."""
    stats = declividade.select("declividade").reduceRegion(
        reducer=ee.Reducer.mean()
        .combine(ee.Reducer.min(), sharedInputs=True)
        .combine(ee.Reducer.max(), sharedInputs=True),
        geometry=geometria,
        scale=30,
        maxPixels=1e9,
    )
    resultado = stats.getInfo()
    return {
        "media": resultado.get("declividade_mean"),
        "minimo": resultado.get("declividade_min"),
        "maximo": resultado.get("declividade_max"),
    }


def classificar_declividade(declividade: ee.Image) -> ee.Image:
    """Classifica declividade conforme EMBRAPA (classes de aptidão agrícola).

    Classes:
    1 = Plano (0-3°) — apto para mecanização
    2 = Suave ondulado (3-8°) — apto com restrições
    3 = Ondulado (8-20°) — uso restrito
    4 = Forte ondulado (20-45°) — preservação recomendada
    5 = Montanhoso/Escarpado (>45°) — preservação obrigatória
    """
    return (
        declividade
        .where(declividade.lte(3), 1)
        .where(declividade.gt(3).And(declividade.lte(8)), 2)
        .where(declividade.gt(8).And(declividade.lte(20)), 3)
        .where(declividade.gt(20).And(declividade.lte(45)), 4)
        .where(declividade.gt(45), 5)
        .rename("classe_declividade")
    )


def calcular_percentual_classes_declividade(
    classes: ee.Image, geometria: ee.Geometry
) -> dict:
    """Calcula o percentual de área em cada classe de declividade."""
    area_por_classe = classes.select("classe_declividade").reduceRegion(
        reducer=ee.Reducer.frequencyHistogram(),
        geometry=geometria,
        scale=30,
        maxPixels=1e9,
    )
    histograma = area_por_classe.get("classe_declividade").getInfo()

    nomes = {
        "1": "Plano (0-3°)",
        "2": "Suave ondulado (3-8°)",
        "3": "Ondulado (8-20°)",
        "4": "Forte ondulado (20-45°)",
        "5": "Montanhoso (>45°)",
    }
    total = sum(histograma.values())
    resultado = {}
    for classe, pixels in sorted(histograma.items()):
        nome = nomes.get(str(int(float(classe))), f"Classe {classe}")
        resultado[nome] = round((pixels / total) * 100, 1)
    return resultado


def gerar_url_tile_elevacao(elevacao: ee.Image, min_elev: float, max_elev: float) -> str:
    """Gera URL de tile do mapa de elevação."""
    vis_params = {
        "bands": ["elevation"],
        "min": min_elev,
        "max": max_elev,
        "palette": ["#313695", "#4575b4", "#74add1", "#abd9e9", "#fee090",
                     "#fdae61", "#f46d43", "#d73027", "#a50026"],
    }
    map_id = elevacao.getMapId(vis_params)
    return map_id["tile_fetcher"].url_format


def gerar_url_tile_declividade(declividade: ee.Image) -> str:
    """Gera URL de tile do mapa de declividade."""
    vis_params = {
        "bands": ["declividade"],
        "min": 0,
        "max": 35,
        "palette": ["#1a9850", "#91cf60", "#d9ef8b", "#fee08b", "#fc8d59", "#d73027"],
    }
    map_id = declividade.getMapId(vis_params)
    return map_id["tile_fetcher"].url_format


def gerar_url_tile_hillshade(hillshade: ee.Image) -> str:
    """Gera URL de tile do hillshade."""
    vis_params = {
        "bands": ["hillshade"],
        "min": 0,
        "max": 255,
        "palette": ["#000000", "#ffffff"],
    }
    map_id = hillshade.getMapId(vis_params)
    return map_id["tile_fetcher"].url_format


def gerar_url_tile_classes_declividade(classes: ee.Image) -> str:
    """Gera URL de tile das classes de declividade (EMBRAPA)."""
    vis_params = {
        "bands": ["classe_declividade"],
        "min": 1,
        "max": 5,
        "palette": ["#1a9850", "#a6d96a", "#fee08b", "#f46d43", "#d73027"],
    }
    map_id = classes.getMapId(vis_params)
    return map_id["tile_fetcher"].url_format


def classificar_aspecto_cardinal(aspecto: ee.Image) -> ee.Image:
    """Classifica aspecto em 8 direções cardinais + plano.

    Classes: 1=N 2=NE 3=E 4=SE 5=S 6=SW 7=W 8=NW
    Aspecto em graus (0–360, 0 = Norte).
    """
    a = aspecto.select("aspecto")
    return (
        a
        .where(a.gte(337.5).Or(a.lt(22.5)), 1)   # N
        .where(a.gte(22.5).And(a.lt(67.5)), 2)   # NE
        .where(a.gte(67.5).And(a.lt(112.5)), 3)  # E
        .where(a.gte(112.5).And(a.lt(157.5)), 4) # SE
        .where(a.gte(157.5).And(a.lt(202.5)), 5) # S
        .where(a.gte(202.5).And(a.lt(247.5)), 6) # SW
        .where(a.gte(247.5).And(a.lt(292.5)), 7) # W
        .where(a.gte(292.5).And(a.lt(337.5)), 8) # NW
        .rename("aspect_class")
    )


def calcular_percentual_aspecto(aspect_classes: ee.Image, geometria: ee.Geometry) -> dict:
    """Retorna percentual de área em cada face cardinal."""
    hist = aspect_classes.reduceRegion(
        reducer=ee.Reducer.frequencyHistogram(),
        geometry=geometria, scale=30, maxPixels=1e9,
    ).get("aspect_class").getInfo() or {}
    nomes = {"1": "N", "2": "NE", "3": "E", "4": "SE",
             "5": "S", "6": "SW", "7": "W", "8": "NW"}
    total = sum(hist.values()) or 1
    return {nomes.get(str(int(float(k))), k): round((v/total)*100, 1)
            for k, v in hist.items()}


def calcular_risco_erosao(composto: ee.Image, elevacao: ee.Image, geometria: ee.Geometry) -> ee.Image:
    """Calcula índice de risco de erosão combinando declividade e solo exposto.

    Risco = 0.6 * slope_score + 0.4 * bsi_score
    - slope_score: declividade normalizada (0° = 0 ; 45° = 1)
    - bsi_score: BSI normalizado (−0.1 = 0 ; 0.2 = 1)
    Resultado classificado em 3 níveis:
      1 = Baixo (< 0.35)
      2 = Médio (0.35–0.55)
      3 = Alto (> 0.55)
    """
    slope = ee.Terrain.slope(elevacao).rename("slope_tmp")
    bsi = composto.select("BSI")
    slope_score = slope.divide(45).clamp(0, 1)
    bsi_score = bsi.subtract(-0.1).divide(0.3).clamp(0, 1)
    risco_cont = slope_score.multiply(0.6).add(bsi_score.multiply(0.4)).rename("risco_cont")
    risco_classe = (
        risco_cont
        .where(risco_cont.lt(0.35), 1)
        .where(risco_cont.gte(0.35).And(risco_cont.lt(0.55)), 2)
        .where(risco_cont.gte(0.55), 3)
        .rename("risco_erosao")
    )
    return risco_classe.clip(geometria)


def calcular_percentual_risco_erosao(risco: ee.Image, geometria: ee.Geometry) -> dict:
    """Retorna percentual de área em cada classe de risco de erosão."""
    hist = risco.reduceRegion(
        reducer=ee.Reducer.frequencyHistogram(),
        geometry=geometria, scale=30, maxPixels=1e9,
    ).get("risco_erosao").getInfo() or {}
    nomes = {"1": "baixo", "2": "medio", "3": "alto"}
    total = sum(hist.values()) or 1
    out = {"baixo": 0.0, "medio": 0.0, "alto": 0.0}
    for k, v in hist.items():
        key = nomes.get(str(int(float(k))))
        if key:
            out[key] = round((v/total)*100, 1)
    return out


def gerar_url_tile_risco_erosao(risco: ee.Image) -> str:
    """Gera URL de tile do mapa de risco de erosão (3 classes)."""
    vis_params = {
        "bands": ["risco_erosao"],
        "min": 1, "max": 3,
        "palette": ["#1a9850", "#fee08b", "#d73027"],  # verde / amarelo / vermelho
    }
    map_id = risco.getMapId(vis_params)
    return map_id["tile_fetcher"].url_format


def obter_estatisticas_aspecto(aspecto: ee.Image, geometria: ee.Geometry) -> dict:
    """Média vetorial circular do aspecto (evita média errada em 0°/360°)."""
    import math
    a_rad = aspecto.select("aspecto").multiply(math.pi / 180)
    sin_mean = a_rad.sin().reduceRegion(
        reducer=ee.Reducer.mean(), geometry=geometria, scale=30, maxPixels=1e9
    ).get("aspecto").getInfo() or 0
    cos_mean = a_rad.cos().reduceRegion(
        reducer=ee.Reducer.mean(), geometry=geometria, scale=30, maxPixels=1e9
    ).get("aspecto").getInfo() or 0
    mean_rad = math.atan2(sin_mean, cos_mean)
    mean_deg = (math.degrees(mean_rad) + 360) % 360
    # Concentração (1 = tudo na mesma direção, 0 = disperso)
    r = math.sqrt(sin_mean**2 + cos_mean**2)
    return {"media_graus": mean_deg, "concentracao": r}


# ============================================================
# Classificação de Uso do Solo
# ============================================================

def classificar_uso_solo(
    colecao: ee.ImageCollection,
    geometria: ee.Geometry,
    n_classes: int = 5,
) -> ee.Image:
    """Classifica uso do solo com K-Means clustering não supervisionado.

    Classes resultantes (ordenadas por NDVI médio):
    1 = Água / sombra
    2 = Solo exposto / construções
    3 = Vegetação rala (pastagem seca)
    4 = Vegetação moderada (pastagem verde / cultivo)
    5 = Vegetação densa (mata)
    """
    composto = colecao.map(adicionar_indices).median().clip(geometria)
    bandas = composto.select(["B2", "B3", "B4", "B8", "B11", "B12", "NDVI", "NDWI", "BSI"])

    amostra = bandas.sample(region=geometria, scale=10, numPixels=5000, seed=42)
    clusterer = ee.Clusterer.wekaKMeans(n_classes).train(amostra)
    resultado = bandas.cluster(clusterer).rename("cluster")

    # Calcular NDVI médio por cluster (client-side) e ordenar
    ndvi_por_cluster = []
    for i in range(n_classes):
        mask = resultado.eq(i)
        mean_ndvi = composto.select("NDVI").updateMask(mask).reduceRegion(
            reducer=ee.Reducer.mean(), geometry=geometria, scale=10, maxPixels=1e9,
        ).get("NDVI").getInfo()
        ndvi_por_cluster.append((i, mean_ndvi if mean_ndvi else 0))

    # Ordenar clusters por NDVI (menor = classe 1, maior = classe 5)
    ndvi_por_cluster.sort(key=lambda x: x[1])
    from_vals = [c[0] for c in ndvi_por_cluster]
    to_vals = list(range(1, n_classes + 1))

    classificado = resultado.remap(from_vals, to_vals).rename("uso_solo")
    return classificado


def calcular_percentual_uso_solo(classificado: ee.Image, geometria: ee.Geometry) -> dict:
    """Calcula percentual de cada classe de uso do solo."""
    histograma = classificado.select("uso_solo").reduceRegion(
        reducer=ee.Reducer.frequencyHistogram(),
        geometry=geometria,
        scale=10,
        maxPixels=1e9,
    ).get("uso_solo").getInfo()

    nomes = {
        "1": "Água / Sombra",
        "2": "Solo exposto / Construções",
        "3": "Vegetação rala (pastagem seca)",
        "4": "Vegetação moderada (pastagem/cultivo)",
        "5": "Vegetação densa (mata)",
    }
    total = sum(histograma.values())
    resultado = {}
    for classe, pixels in sorted(histograma.items()):
        nome = nomes.get(str(int(float(classe))), f"Classe {classe}")
        resultado[nome] = round((pixels / total) * 100, 1)
    return resultado


def gerar_url_tile_uso_solo(classificado: ee.Image) -> str:
    """Gera URL de tile do mapa de uso do solo."""
    vis_params = {
        "bands": ["uso_solo"],
        "min": 1,
        "max": 5,
        "palette": [
            "#2166ac",  # 1 - Água/sombra (azul)
            "#d6604d",  # 2 - Solo exposto (vermelho)
            "#f4a582",  # 3 - Veg. rala (salmão)
            "#92c5de",  # 4 - Veg. moderada (azul claro)
            "#1b7837",  # 5 - Mata (verde escuro)
        ],
    }
    map_id = classificado.getMapId(vis_params)
    return map_id["tile_fetcher"].url_format


# ============================================================
# Análise de Água e Umidade
# ============================================================

def calcular_twi(elevacao: ee.Image, geometria: ee.Geometry) -> ee.Image:
    """Calcula o Índice de Umidade Topográfica simplificado.

    Combina elevação invertida com declividade para estimar
    onde a água tende a se acumular no terreno.

    Valores altos = áreas úmidas, acúmulo de água (vales, baixadas)
    Valores baixos = áreas secas (topos, encostas íngremes)
    """
    slope_rad = ee.Terrain.slope(elevacao).multiply(3.14159 / 180)

    # Inverter elevação: áreas mais baixas recebem valores maiores
    elev = elevacao.select("elevation")
    elev_max = ee.Number(elev.reduceRegion(
        reducer=ee.Reducer.max(), geometry=geometria, scale=30, maxPixels=1e9
    ).get("elevation"))
    elev_invertida = ee.Image(elev_max).subtract(elev).add(1)

    # TWI simplificado: log(elevação invertida) / tan(declividade)
    slope_safe = slope_rad.where(slope_rad.lt(0.01), 0.01)
    twi = elev_invertida.log().divide(slope_safe.tan().add(0.001)).rename("TWI")

    return twi.clip(geometria)


def calcular_ndwi_agua(colecao: ee.ImageCollection, geometria: ee.Geometry) -> ee.Image:
    """Calcula NDWI médio para detectar presença de água.

    NDWI = (GREEN - NIR) / (GREEN + NIR)
    Valores > 0 indicam presença de água
    """
    def add_ndwi(img):
        return img.addBands(img.normalizedDifference(["B3", "B8"]).rename("NDWI_agua"))

    return colecao.map(add_ndwi).select("NDWI_agua").median().clip(geometria)


def gerar_url_tile_twi(twi: ee.Image) -> str:
    """Gera URL de tile do mapa TWI (umidade topográfica)."""
    vis_params = {
        "bands": ["TWI"],
        "min": -2,
        "max": 5,
        "palette": ["#d73027", "#fc8d59", "#fee08b", "#d9ef8b", "#91cf60", "#1a9850", "#00441b"],
    }
    map_id = twi.getMapId(vis_params)
    return map_id["tile_fetcher"].url_format


def gerar_url_tile_ndwi(ndwi: ee.Image) -> str:
    """Gera URL de tile do NDWI (detecção de água)."""
    vis_params = {
        "bands": ["NDWI_agua"],
        "min": -0.5,
        "max": 0.5,
        "palette": ["#d73027", "#fee08b", "#d9ef8b", "#91cf60", "#4575b4", "#313695"],
    }
    map_id = ndwi.getMapId(vis_params)
    return map_id["tile_fetcher"].url_format


def obter_estatisticas_twi(twi: ee.Image, geometria: ee.Geometry) -> dict:
    """Estatísticas do TWI: média, min, max, percentual de pixels por faixa."""
    stats = twi.reduceRegion(
        reducer=ee.Reducer.mean().combine(ee.Reducer.minMax(), sharedInputs=True)
                                   .combine(ee.Reducer.stdDev(), sharedInputs=True),
        geometry=geometria, scale=30, maxPixels=1e9,
    ).getInfo()
    return {
        "media": stats.get("TWI_mean", 0) or 0,
        "minimo": stats.get("TWI_min", 0) or 0,
        "maximo": stats.get("TWI_max", 0) or 0,
        "desvio": stats.get("TWI_stdDev", 0) or 0,
    }


def obter_ponto_twi_maximo(twi: ee.Image, geometria: ee.Geometry) -> dict:
    """Retorna lat/lon do pixel de TWI máximo (melhor candidato a tanque/nascente)."""
    # Anexa coordenadas como bandas
    coords = ee.Image.pixelLonLat()
    stack = twi.addBands(coords)
    max_info = stack.reduceRegion(
        reducer=ee.Reducer.max(numInputs=3),
        geometry=geometria, scale=30, maxPixels=1e9,
        bestEffort=True,
    ).getInfo()
    # Resultado: {'max': twi_val, 'max1': lon, 'max2': lat}
    return {
        "twi": max_info.get("max"),
        "lon": max_info.get("max1"),
        "lat": max_info.get("max2"),
    }


def obter_percentuais_twi(twi: ee.Image, geometria: ee.Geometry) -> dict:
    """Percentual de área em 3 faixas: seca, moderada, úmida."""
    # Classifica em 3 faixas: < 0.5 seco, 0.5-2 moderado, > 2 úmido
    seco = twi.lt(0.5).rename("seco")
    moderado = twi.gte(0.5).And(twi.lt(2)).rename("moderado")
    umido = twi.gte(2).rename("umido")
    stack = seco.addBands(moderado).addBands(umido)
    stats = stack.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=geometria, scale=30, maxPixels=1e9,
    ).getInfo()
    return {
        "seco": (stats.get("seco", 0) or 0) * 100,
        "moderado": (stats.get("moderado", 0) or 0) * 100,
        "umido": (stats.get("umido", 0) or 0) * 100,
    }


def obter_estatisticas_ndwi(ndwi: ee.Image, geometria: ee.Geometry) -> dict:
    """Estatísticas do NDWI e percentual de pixels com água (> 0)."""
    stats = ndwi.reduceRegion(
        reducer=ee.Reducer.mean().combine(ee.Reducer.minMax(), sharedInputs=True),
        geometry=geometria, scale=10, maxPixels=1e9,
    ).getInfo()
    # % pixels com NDWI > 0 (água efetiva)
    agua = ndwi.gt(0).rename("agua")
    pct_agua = agua.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=geometria, scale=10, maxPixels=1e9,
    ).getInfo()
    # Total de pixels amostrados
    total = ndwi.reduceRegion(
        reducer=ee.Reducer.count(), geometry=geometria, scale=10, maxPixels=1e9,
    ).getInfo()
    return {
        "media": stats.get("NDWI_agua_mean", 0) or 0,
        "minimo": stats.get("NDWI_agua_min", 0) or 0,
        "maximo": stats.get("NDWI_agua_max", 0) or 0,
        "pct_agua": (pct_agua.get("agua", 0) or 0) * 100,
        "n_pixels": total.get("NDWI_agua", 0) or 0,
    }


# ============================================================
# Clima histórico (CHIRPS + ERA5)
# ============================================================

def extrair_serie_chuva_mensal(geometria: ee.Geometry, ano_inicio: int = 2015, ano_fim: int = 2024) -> "pd.DataFrame":
    """Série mensal de precipitação usando CHIRPS (0,05° ≈ 5 km).

    Geometrias menores que o pixel CHIRPS (~5 km) retornam NaN em reduceRegion
    com a própria geometria; usamos o centróide para amostrar o pixel central.
    """
    import pandas as pd
    ponto = geometria.centroid(1)
    chirps = (
        ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
        .filterDate(f"{ano_inicio}-01-01", f"{ano_fim+1}-01-01")
        .filterBounds(geometria)
        .select("precipitation")
    )
    registros = []
    for mes in range(1, 13):
        filtrada = chirps.filter(ee.Filter.calendarRange(mes, mes, "month"))
        # Total mensal médio: dias * média diária
        val = filtrada.mean().multiply(30).reduceRegion(
            reducer=ee.Reducer.mean(), geometry=ponto, scale=5566, maxPixels=1e9
        ).get("precipitation").getInfo() or 0
        registros.append({"mes": mes, "precipitacao_mm": val})
    return pd.DataFrame(registros)


def extrair_serie_temperatura_mensal(geometria: ee.Geometry, ano_inicio: int = 2015, ano_fim: int = 2024) -> "pd.DataFrame":
    """Série mensal de temperatura (média, min, max) a partir do ERA5-Land diário.

    Para cada mês (1..12), agrega em toda a janela ano_inicio..ano_fim:
      - temp_media_c: média das médias diárias
      - temp_min_c:   mínima observada (mínima diária mínima)
      - temp_max_c:   máxima observada (máxima diária máxima)
    Temperaturas vêm em Kelvin no ERA5 → convertemos para °C.
    """
    import pandas as pd
    # Geometria do sítio é menor que o pixel ERA5 (~11 km) -> amostrar no centróide
    ponto = geometria.centroid(1)
    era5 = (
        ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR")
        .filterDate(f"{ano_inicio}-01-01", f"{ano_fim+1}-01-01")
        .filterBounds(geometria)
        .select(["temperature_2m", "temperature_2m_min", "temperature_2m_max"])
    )
    registros = []
    for mes in range(1, 13):
        filtrada = era5.filter(ee.Filter.calendarRange(mes, mes, "month"))
        media_img = filtrada.select("temperature_2m").mean()
        min_img = filtrada.select("temperature_2m_min").min()
        max_img = filtrada.select("temperature_2m_max").max()
        stack = media_img.rename("t_mean").addBands(min_img.rename("t_min")).addBands(max_img.rename("t_max"))
        vals = stack.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=ponto, scale=11132, maxPixels=1e9
        ).getInfo() or {}
        def _c(k):
            v = vals.get(k)
            return v - 273.15 if v is not None else None
        registros.append({
            "mes": mes,
            "temp_media_c": _c("t_mean"),
            "temp_min_c": _c("t_min"),
            "temp_max_c": _c("t_max"),
        })
    return pd.DataFrame(registros)
