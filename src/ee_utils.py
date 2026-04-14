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
