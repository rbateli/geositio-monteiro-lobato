"""Gera relatório completo do sítio: mapa + dados + gráficos + interpretação."""
import sys
sys.path.append(".")

import base64
import json
from pathlib import Path

import folium
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import pandas as pd

from src.config import SITIO_CENTER
from src.geo_utils import carregar_sitio, reprojetar
from src.ee_utils import (
    inicializar_ee,
    carregar_geometria_sitio,
    coletar_sentinel2,
    composto_mediana,
    extrair_serie_temporal_ndvi,
    obter_estatisticas_ndvi,
    gerar_url_tile_ndvi,
    gerar_url_tile_rgb,
    carregar_elevacao,
    calcular_declividade,
    calcular_hillshade,
    classificar_declividade,
    obter_estatisticas_elevacao,
    obter_estatisticas_declividade,
    calcular_percentual_classes_declividade,
    gerar_url_tile_elevacao,
    gerar_url_tile_declividade,
    gerar_url_tile_hillshade,
    gerar_url_tile_classes_declividade,
)

print("Inicializando Earth Engine...")
inicializar_ee()
geometria = carregar_geometria_sitio()

# --- Dados da propriedade ---
gdf_sitio = carregar_sitio()
gdf_utm = reprojetar(gdf_sitio)
area_m2 = gdf_utm.area.values[0]
perimetro_m = gdf_utm.length.values[0]

# --- NDVI atual ---
print("Coletando imagens Sentinel-2...")
colecao = coletar_sentinel2(geometria, "2025-04-01", "2026-04-01", max_nuvens=20)
qtd_imagens = colecao.size().getInfo()
composto = composto_mediana(colecao, geometria)
stats = obter_estatisticas_ndvi(composto, geometria)

# --- Série temporal ---
print("Extraindo série temporal NDVI (3 anos)...")
df_ndvi = extrair_serie_temporal_ndvi(geometria, "2023-04-01", "2026-04-09", max_nuvens=30)

# --- Relevo ---
print("Processando dados de relevo (SRTM)...")
elevacao = carregar_elevacao(geometria)
declividade_img = calcular_declividade(elevacao)
hillshade = calcular_hillshade(elevacao)
classes_decl = classificar_declividade(declividade_img)
stats_elev = obter_estatisticas_elevacao(elevacao, geometria)
stats_decl = obter_estatisticas_declividade(declividade_img, geometria)
pct_classes = calcular_percentual_classes_declividade(classes_decl, geometria)

# --- URLs dos tiles ---
print("Gerando camadas do mapa...")
url_ndvi = gerar_url_tile_ndvi(composto)
url_rgb = gerar_url_tile_rgb(composto)
url_elev = gerar_url_tile_elevacao(elevacao, stats_elev["minimo"], stats_elev["maximo"])
url_decl = gerar_url_tile_declividade(declividade_img)
url_hill = gerar_url_tile_hillshade(hillshade)
url_classes = gerar_url_tile_classes_declividade(classes_decl)

# --- Gráfico série temporal ---
cores_ndvi = ["#d73027", "#f46d43", "#fdae61", "#fee08b", "#d9ef8b", "#a6d96a", "#66bd63", "#1a9850"]
cmap = mcolors.LinearSegmentedColormap.from_list("ndvi", cores_ndvi)
norm = mcolors.Normalize(vmin=0.1, vmax=0.7)

fig, ax = plt.subplots(figsize=(12, 4))
ax.plot(df_ndvi["data"], df_ndvi["ndvi_medio"], color="#555555", alpha=0.4, linewidth=1, zorder=1)
scatter = ax.scatter(df_ndvi["data"], df_ndvi["ndvi_medio"], c=df_ndvi["ndvi_medio"],
                     cmap=cmap, norm=norm, s=40, edgecolors="white", linewidth=0.5, zorder=2)
df_ndvi["media_movel"] = df_ndvi["ndvi_medio"].rolling(window=5, center=True).mean()
ax.plot(df_ndvi["data"], df_ndvi["media_movel"], color="#1a9850", linewidth=2.5, label="Média móvel", zorder=3)
ax.axhline(y=0.4, color="#fdae61", linestyle="--", alpha=0.5, label="Vegetação moderada")
ax.axhline(y=0.6, color="#66bd63", linestyle="--", alpha=0.5, label="Vegetação densa")
ax.set_ylabel("NDVI Médio")
ax.legend(loc="lower right", fontsize=8)
ax.grid(True, alpha=0.2)
ax.set_ylim(0, 0.85)
plt.colorbar(scatter, ax=ax, label="NDVI", shrink=0.8)
plt.tight_layout()
plt.savefig("data/chart_serie.png", dpi=150, bbox_inches="tight")
plt.close()

# --- Gráfico sazonal ---
df_ndvi["mes"] = df_ndvi["data"].dt.month
meses = {1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}
sazonal = df_ndvi.groupby("mes")["ndvi_medio"].agg(["mean","std"]).reset_index()
sazonal["mes_nome"] = sazonal["mes"].map(meses)

fig, ax = plt.subplots(figsize=(10, 4))
cores_mes = [cmap(norm(v)) for v in sazonal["mean"]]
ax.bar(sazonal["mes_nome"], sazonal["mean"], color=cores_mes, edgecolor="white")
ax.errorbar(sazonal["mes_nome"], sazonal["mean"], yerr=sazonal["std"], fmt="none", color="#333", capsize=4)
ax.set_ylabel("NDVI Médio")
ax.set_ylim(0, 0.85)
ax.grid(True, alpha=0.2, axis="y")
mes_max = sazonal.loc[sazonal["mean"].idxmax()]
mes_min = sazonal.loc[sazonal["mean"].idxmin()]
ax.annotate(f"Mais verde\n{mes_max['mean']:.2f}", xy=(mes_max["mes"]-1, mes_max["mean"]),
            xytext=(0, 15), textcoords="offset points", ha="center", fontsize=9, color="#1a9850", fontweight="bold")
ax.annotate(f"Mais seco\n{mes_min['mean']:.2f}", xy=(mes_min["mes"]-1, mes_min["mean"]),
            xytext=(0, 15), textcoords="offset points", ha="center", fontsize=9, color="#d73027", fontweight="bold")
plt.tight_layout()
plt.savefig("data/chart_sazonal.png", dpi=150, bbox_inches="tight")
plt.close()

# --- Converter gráficos para base64 ---
def img_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

# --- Gráfico classes declividade ---
cores_classes = ["#1a9850", "#a6d96a", "#fee08b", "#f46d43", "#d73027"]
labels_cl = list(pct_classes.keys())
valores_cl = list(pct_classes.values())
cores_cl = cores_classes[:len(labels_cl)]

fig, ax = plt.subplots(figsize=(10, 4))
bars = ax.barh(labels_cl, valores_cl, color=cores_cl, edgecolor="white", linewidth=0.5)
ax.set_xlabel("% da Área")
ax.set_title("Aptidão Agrícola por Declividade — EMBRAPA", fontweight="bold")
ax.grid(True, alpha=0.2, axis="x")
for bar, val in zip(bars, valores_cl):
    ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
            f"{val}%", va="center", fontsize=10, fontweight="bold")
ax.invert_yaxis()
plt.tight_layout()
plt.savefig("data/chart_declividade.png", dpi=150, bbox_inches="tight")
plt.close()

chart_serie_b64 = img_to_base64("data/chart_serie.png")
chart_sazonal_b64 = img_to_base64("data/chart_sazonal.png")
chart_decl_b64 = img_to_base64("data/chart_declividade.png")

# --- Gerar mapa Folium ---
mapa = folium.Map(location=SITIO_CENTER, zoom_start=17, tiles=None)

folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    name="Satélite (Esri)", attr="Esri",
).add_to(mapa)

folium.TileLayer(tiles=url_rgb, name="Sentinel-2 (Cor Real)",
                 attr="ESA Copernicus", overlay=False).add_to(mapa)

folium.TileLayer(tiles=url_ndvi, name="NDVI (Saúde da Vegetação)",
                 attr="ESA Copernicus", overlay=False).add_to(mapa)

folium.TileLayer(tiles=url_hill, name="Relevo 3D",
                 attr="SRTM/NASA", overlay=False).add_to(mapa)

folium.TileLayer(tiles=url_elev, name="Elevação (metros)",
                 attr="SRTM/NASA", overlay=False).add_to(mapa)

folium.TileLayer(tiles=url_decl, name="Declividade (graus)",
                 attr="SRTM/NASA", overlay=False).add_to(mapa)

folium.TileLayer(tiles=url_classes, name="Aptidão Agrícola (EMBRAPA)",
                 attr="SRTM/NASA", overlay=False).add_to(mapa)

folium.GeoJson(gdf_sitio.to_json(), name="Limite do Sítio",
               style_function=lambda x: {"fillColor":"transparent","color":"#FFD700","weight":3,"fillOpacity":0}).add_to(mapa)

folium.CircleMarker(location=SITIO_CENTER, radius=6, color="#FFD700", fill=True,
                    fill_color="#228B22", fill_opacity=0.8).add_to(mapa)

folium.LayerControl().add_to(mapa)
mapa_html = mapa._repr_html_()

# --- Interpretação automática ---
ndvi_medio = stats["media"]
if ndvi_medio >= 0.6:
    estado = "saudável"
    estado_cor = "#1a9850"
    interpretacao = "A vegetação do sítio está em bom estado geral, com cobertura densa predominante."
elif ndvi_medio >= 0.4:
    estado = "moderado"
    estado_cor = "#fdae61"
    interpretacao = "A vegetação está em estado moderado. Algumas áreas podem precisar de atenção."
else:
    estado = "em alerta"
    estado_cor = "#d73027"
    interpretacao = "A vegetação está em estado preocupante. Recomenda-se verificar áreas degradadas."

# Tendência
ndvi_inicio = df_ndvi.head(10)["ndvi_medio"].mean()
ndvi_fim = df_ndvi.tail(10)["ndvi_medio"].mean()
variacao = ((ndvi_fim - ndvi_inicio) / ndvi_inicio) * 100
if variacao > 5:
    tendencia = f"melhoria de {variacao:.1f}%"
    tend_cor = "#1a9850"
elif variacao < -5:
    tendencia = f"queda de {abs(variacao):.1f}%"
    tend_cor = "#d73027"
else:
    tendencia = f"estável ({variacao:+.1f}%)"
    tend_cor = "#666666"

# Mês mais verde e mais seco
mes_verde = meses[int(mes_max["mes"])]
mes_seco = meses[int(mes_min["mes"])]

# --- Montar HTML ---
html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GeoSítio — Relatório de Inteligência Geoespacial</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #0f1117; color: #e0e0e0; }}
        .header {{ background: linear-gradient(135deg, #1a3a2a, #0f1117); padding: 40px; text-align: center; border-bottom: 2px solid #1a9850; }}
        .header h1 {{ font-size: 2.2em; color: #fff; margin-bottom: 8px; }}
        .header p {{ color: #a0a0a0; font-size: 1.1em; }}
        .container {{ max-width: 1400px; margin: 0 auto; padding: 30px; }}

        /* Cards de métricas */
        .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 30px; }}
        .metric-card {{ background: #1a1d27; border-radius: 12px; padding: 24px; text-align: center; border: 1px solid #2a2d37; }}
        .metric-card .value {{ font-size: 2em; font-weight: 700; color: #fff; }}
        .metric-card .label {{ font-size: 0.85em; color: #888; margin-top: 4px; text-transform: uppercase; letter-spacing: 1px; }}
        .metric-card .sub {{ font-size: 0.8em; color: #666; margin-top: 2px; }}

        /* Seções */
        .section {{ background: #1a1d27; border-radius: 12px; padding: 30px; margin-bottom: 24px; border: 1px solid #2a2d37; }}
        .section h2 {{ color: #1a9850; font-size: 1.4em; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 1px solid #2a2d37; }}
        .section p {{ line-height: 1.7; color: #ccc; }}

        /* Mapa */
        .map-container {{ height: 500px; border-radius: 8px; overflow: hidden; margin: 16px 0; }}
        .map-container iframe {{ width: 100%; height: 100%; border: none; }}

        /* Gráficos */
        .chart {{ text-align: center; margin: 16px 0; }}
        .chart img {{ max-width: 100%; border-radius: 8px; }}

        /* Legenda NDVI */
        .legenda {{ display: flex; align-items: center; gap: 8px; margin: 16px 0; flex-wrap: wrap; }}
        .legenda-item {{ display: flex; align-items: center; gap: 4px; font-size: 0.85em; }}
        .legenda-cor {{ width: 16px; height: 16px; border-radius: 3px; }}

        /* Status */
        .status {{ display: inline-block; padding: 4px 12px; border-radius: 20px; font-weight: 600; font-size: 0.9em; }}

        /* Insights */
        .insights {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; margin-top: 16px; }}
        .insight {{ background: #12141c; border-radius: 8px; padding: 20px; border-left: 4px solid #1a9850; }}
        .insight h3 {{ color: #fff; font-size: 1em; margin-bottom: 8px; }}
        .insight p {{ font-size: 0.9em; color: #aaa; line-height: 1.6; }}

        /* Footer */
        .footer {{ text-align: center; padding: 30px; color: #555; font-size: 0.85em; border-top: 1px solid #2a2d37; margin-top: 30px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>GeoSítio — Monteiro Lobato</h1>
        <p>Relatório de Inteligência Geoespacial | Atualizado em abril/2026</p>
    </div>

    <div class="container">
        <!-- Métricas principais -->
        <div class="metrics">
            <div class="metric-card">
                <div class="value">{area_m2/10_000:.2f} ha</div>
                <div class="label">Área total</div>
                <div class="sub">{area_m2:,.0f} m²</div>
            </div>
            <div class="metric-card">
                <div class="value">{perimetro_m:,.0f} m</div>
                <div class="label">Perímetro</div>
            </div>
            <div class="metric-card">
                <div class="value" style="color: {estado_cor}">{stats['media']:.3f}</div>
                <div class="label">NDVI Médio</div>
                <div class="sub">Estado: <span class="status" style="background: {estado_cor}22; color: {estado_cor}">{estado}</span></div>
            </div>
            <div class="metric-card">
                <div class="value" style="color: {tend_cor}">{tendencia}</div>
                <div class="label">Tendência 3 anos</div>
            </div>
            <div class="metric-card">
                <div class="value">{stats_elev['minimo']:.0f}–{stats_elev['maximo']:.0f} m</div>
                <div class="label">Elevação</div>
                <div class="sub">Desnível: {stats_elev['desnivel']:.0f} m</div>
            </div>
            <div class="metric-card">
                <div class="value">{stats_decl['media']:.1f}°</div>
                <div class="label">Declividade média</div>
                <div class="sub">Máx: {stats_decl['maximo']:.1f}°</div>
            </div>
            <div class="metric-card">
                <div class="value">{qtd_imagens}</div>
                <div class="label">Imagens analisadas</div>
                <div class="sub">Sentinel-2 (último ano)</div>
            </div>
            <div class="metric-card">
                <div class="value">{len(df_ndvi)}</div>
                <div class="label">Observações</div>
                <div class="sub">Série temporal (3 anos)</div>
            </div>
        </div>

        <!-- Mapa -->
        <div class="section">
            <h2>Mapa Interativo da Propriedade</h2>
            <p>Alterne entre as camadas no canto superior direito: Satélite, Sentinel-2, NDVI, Elevação, Declividade, Relevo 3D e Aptidão Agrícola.</p>
            <div class="map-container">
                {mapa_html}
            </div>
            <div class="legenda">
                <span style="font-weight:600; margin-right:8px;">Legenda NDVI:</span>
                <div class="legenda-item"><div class="legenda-cor" style="background:#d73027"></div> Solo exposto</div>
                <div class="legenda-item"><div class="legenda-cor" style="background:#fdae61"></div> Vegetação rala</div>
                <div class="legenda-item"><div class="legenda-cor" style="background:#fee08b"></div> Pastagem seca</div>
                <div class="legenda-item"><div class="legenda-cor" style="background:#d9ef8b"></div> Vegetação moderada</div>
                <div class="legenda-item"><div class="legenda-cor" style="background:#66bd63"></div> Vegetação densa</div>
                <div class="legenda-item"><div class="legenda-cor" style="background:#1a9850"></div> Mata saudável</div>
            </div>
        </div>

        <!-- Relevo -->
        <div class="section">
            <h2>Análise de Relevo e Declividade</h2>
            <p>Dados do SRTM (NASA) — resolução de 30m. A declividade é classificada conforme critérios da EMBRAPA para aptidão agrícola.</p>
            <div class="insights">
                <div class="insight">
                    <h3>Elevação</h3>
                    <p>O sítio varia de <strong>{stats_elev['minimo']:.0f}m</strong> a <strong>{stats_elev['maximo']:.0f}m</strong> de altitude,
                    com desnível de <strong>{stats_elev['desnivel']:.0f}m</strong>. Altitude média de {stats_elev['media']:.0f}m,
                    típica da Serra da Mantiqueira.</p>
                </div>
                <div class="insight">
                    <h3>Declividade</h3>
                    <p>Declividade média de <strong>{stats_decl['media']:.1f}°</strong> (máxima de {stats_decl['maximo']:.1f}°).
                    Terreno predominantemente <strong>ondulado</strong>, com áreas mais íngremes que exigem cuidado com erosão.</p>
                </div>
                <div class="insight" style="border-left-color: #a6d96a">
                    <h3>Aptidão agrícola</h3>
                    <p>{"<br>".join(f"<strong>{k}:</strong> {v}% da área" for k, v in pct_classes.items())}</p>
                </div>
                <div class="insight" style="border-left-color: #f46d43">
                    <h3>Recomendação</h3>
                    <p>As áreas de declividade forte ({pct_classes.get('Forte ondulado (20-45°)', 0)}% do sítio) devem ser
                    destinadas à preservação ou pastagem extensiva. As áreas suave onduladas
                    ({pct_classes.get('Suave ondulado (3-8°)', 0)}%) são as mais indicadas para cultivo.</p>
                </div>
            </div>
            <div class="chart">
                <img src="data:image/png;base64,{chart_decl_b64}" alt="Classes de declividade">
            </div>
        </div>

        <!-- Interpretação -->
        <div class="section">
            <h2>Diagnóstico da Vegetação</h2>
            <p>{interpretacao}</p>
            <div class="insights">
                <div class="insight">
                    <h3>Cobertura vegetal</h3>
                    <p>NDVI médio de <strong>{stats['media']:.3f}</strong> indica vegetação {estado}.
                    O valor máximo de <strong>{stats['maximo']:.3f}</strong> nas áreas de mata mostra vegetação densa e preservada.
                    O mínimo de <strong>{stats['minimo']:.3f}</strong> corresponde a áreas construídas (telhados).</p>
                </div>
                <div class="insight">
                    <h3>Variabilidade espacial</h3>
                    <p>Desvio padrão de <strong>{stats['desvio_padrao']:.3f}</strong> indica que o sítio tem
                    diversidade de coberturas — áreas de mata densa, pastagem e construções,
                    o que é típico de uma propriedade rural mista.</p>
                </div>
                <div class="insight">
                    <h3>Sazonalidade</h3>
                    <p>O mês mais verde é <strong>{mes_verde}</strong> e o mais seco é <strong>{mes_seco}</strong>.
                    Isso reflete o regime de chuvas da Serra da Mantiqueira — verão úmido e inverno seco.</p>
                </div>
                <div class="insight">
                    <h3>Tendência temporal</h3>
                    <p>Nos últimos 3 anos, a vegetação apresenta <strong style="color:{tend_cor}">{tendencia}</strong>.
                    A análise considera {len(df_ndvi)} observações do satélite Sentinel-2.</p>
                </div>
            </div>
        </div>

        <!-- Série temporal -->
        <div class="section">
            <h2>Evolução da Vegetação (2023–2026)</h2>
            <p>Cada ponto representa o NDVI médio do sítio em uma passagem do Sentinel-2. A linha verde é a média móvel.</p>
            <div class="chart">
                <img src="data:image/png;base64,{chart_serie_b64}" alt="Série temporal NDVI">
            </div>
        </div>

        <!-- Sazonal -->
        <div class="section">
            <h2>Ciclo Anual da Vegetação</h2>
            <p>NDVI médio agrupado por mês, mostrando o padrão sazonal da vegetação ao longo do ano.</p>
            <div class="chart">
                <img src="data:image/png;base64,{chart_sazonal_b64}" alt="NDVI sazonal">
            </div>
        </div>
    </div>

    <div class="footer">
        <p>GeoSítio — Inteligência Geoespacial Aplicada à Propriedade Rural</p>
        <p>Dados: ESA Copernicus Sentinel-2 + NASA SRTM | Processamento: Google Earth Engine + Python</p>
    </div>
</body>
</html>"""

Path("data/relatorio_geositio.html").write_text(html, encoding="utf-8")
print("\nRelatório salvo em data/relatorio_geositio.html")
