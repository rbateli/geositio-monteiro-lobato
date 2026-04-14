"""Relatório final GeoSítio — completo, polido, com linguagem para leigos."""
import sys
sys.path.append(".")

import base64
from pathlib import Path

import folium
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import pandas as pd

from src.config import SITIO_CENTER
from src.geo_utils import carregar_sitio, reprojetar
from src.ee_utils import *

# ============================================================
# 1. COLETA DE DADOS
# ============================================================
print("[1/6] Inicializando Earth Engine...")
inicializar_ee()
geometria = carregar_geometria_sitio()
gdf_sitio = carregar_sitio()
gdf_utm = reprojetar(gdf_sitio)
area_m2 = gdf_utm.area.values[0]
perimetro_m = gdf_utm.length.values[0]

print("[2/6] Coletando imagens Sentinel-2 e NDVI...")
colecao = coletar_sentinel2(geometria, "2025-04-01", "2026-04-01", max_nuvens=20)
qtd_imagens = colecao.size().getInfo()
composto = composto_mediana(colecao, geometria)
stats_ndvi = obter_estatisticas_ndvi(composto, geometria)

print("[3/6] Série temporal NDVI (3 anos)...")
df_ndvi = extrair_serie_temporal_ndvi(geometria, "2023-04-01", "2026-04-09", max_nuvens=30)

print("[4/6] Relevo e declividade (SRTM)...")
elevacao = carregar_elevacao(geometria)
declividade_img = calcular_declividade(elevacao)
hillshade = calcular_hillshade(elevacao)
classes_decl = classificar_declividade(declividade_img)
stats_elev = obter_estatisticas_elevacao(elevacao, geometria)
stats_decl = obter_estatisticas_declividade(declividade_img, geometria)
pct_decl = calcular_percentual_classes_declividade(classes_decl, geometria)

print("[5/6] Classificação de uso do solo...")
classificado = classificar_uso_solo(colecao, geometria, n_classes=5)
pct_uso = calcular_percentual_uso_solo(classificado, geometria)

print("[6/6] Análise de água e umidade...")
ndwi = calcular_ndwi_agua(colecao, geometria)
twi = calcular_twi(elevacao, geometria)

# ============================================================
# 2. TILES DO MAPA
# ============================================================
print("Gerando camadas do mapa...")
tiles = {
    "rgb": gerar_url_tile_rgb(composto),
    "ndvi": gerar_url_tile_ndvi(composto),
    "elev": gerar_url_tile_elevacao(elevacao, stats_elev["minimo"], stats_elev["maximo"]),
    "decl": gerar_url_tile_declividade(declividade_img),
    "hill": gerar_url_tile_hillshade(hillshade),
    "classes_decl": gerar_url_tile_classes_declividade(classes_decl),
    "uso": gerar_url_tile_uso_solo(classificado),
    "ndwi": gerar_url_tile_ndwi(ndwi),
    "twi": gerar_url_tile_twi(twi),
}

# ============================================================
# 3. GRÁFICOS
# ============================================================
print("Gerando gráficos...")

plt.rcParams.update({
    "figure.facecolor": "#1a1d27",
    "axes.facecolor": "#12141c",
    "axes.edgecolor": "#2a2d37",
    "text.color": "#e0e0e0",
    "axes.labelcolor": "#ccc",
    "xtick.color": "#888",
    "ytick.color": "#888",
    "grid.color": "#2a2d37",
    "font.family": "sans-serif",
})

cores_ndvi = ["#d73027", "#f46d43", "#fdae61", "#fee08b", "#d9ef8b", "#a6d96a", "#66bd63", "#1a9850"]
cmap_ndvi = mcolors.LinearSegmentedColormap.from_list("ndvi", cores_ndvi)
norm_ndvi = mcolors.Normalize(vmin=0.1, vmax=0.7)

# Série temporal
fig, ax = plt.subplots(figsize=(13, 4.5))
ax.plot(df_ndvi["data"], df_ndvi["ndvi_medio"], color="#555555", alpha=0.3, linewidth=1, zorder=1)
scatter = ax.scatter(df_ndvi["data"], df_ndvi["ndvi_medio"], c=df_ndvi["ndvi_medio"],
                     cmap=cmap_ndvi, norm=norm_ndvi, s=45, edgecolors="#2a2d37", linewidth=0.5, zorder=2)
df_ndvi["mm"] = df_ndvi["ndvi_medio"].rolling(window=5, center=True).mean()
ax.plot(df_ndvi["data"], df_ndvi["mm"], color="#1a9850", linewidth=2.5, label="Tendência", zorder=3)
ax.axhspan(0.6, 0.85, alpha=0.08, color="#1a9850")
ax.axhspan(0.4, 0.6, alpha=0.05, color="#fee08b")
ax.axhspan(0, 0.4, alpha=0.05, color="#d73027")
ax.text(df_ndvi["data"].iloc[-1], 0.72, " Saudável", color="#1a9850", fontsize=8, va="center")
ax.text(df_ndvi["data"].iloc[-1], 0.50, " Moderado", color="#fee08b", fontsize=8, va="center")
ax.text(df_ndvi["data"].iloc[-1], 0.30, " Alerta", color="#d73027", fontsize=8, va="center")
ax.set_ylabel("Índice de Vegetação (NDVI)")
ax.set_ylim(0.1, 0.85)
ax.grid(True, alpha=0.3)
cb = plt.colorbar(scatter, ax=ax, shrink=0.8, pad=0.02)
cb.set_label("NDVI", color="#ccc")
cb.ax.yaxis.set_tick_params(color="#888")
plt.setp(plt.getp(cb.ax.axes, "yticklabels"), color="#888")
plt.tight_layout()
plt.savefig("data/g_serie.png", dpi=150, bbox_inches="tight")
plt.close()

# Sazonal
df_ndvi["mes"] = df_ndvi["data"].dt.month
meses_n = {1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}
sazonal = df_ndvi.groupby("mes")["ndvi_medio"].agg(["mean","std"]).reset_index()
sazonal["nome"] = sazonal["mes"].map(meses_n)

fig, ax = plt.subplots(figsize=(11, 4.5))
cores_m = [cmap_ndvi(norm_ndvi(v)) for v in sazonal["mean"]]
bars = ax.bar(sazonal["nome"], sazonal["mean"], color=cores_m, edgecolor="#2a2d37", linewidth=0.5, width=0.7)
ax.errorbar(sazonal["nome"], sazonal["mean"], yerr=sazonal["std"], fmt="none", color="#888", capsize=3)
ax.set_ylabel("Índice de Vegetação (NDVI)")
ax.set_ylim(0.2, 0.85)
ax.grid(True, alpha=0.3, axis="y")
m_max = sazonal.loc[sazonal["mean"].idxmax()]
m_min = sazonal.loc[sazonal["mean"].idxmin()]
ax.annotate(f"Mais verde\n{m_max['mean']:.2f}", xy=(int(m_max["mes"])-1, m_max["mean"]),
            xytext=(0, 18), textcoords="offset points", ha="center", fontsize=9, color="#1a9850", fontweight="bold")
ax.annotate(f"Mais seco\n{m_min['mean']:.2f}", xy=(int(m_min["mes"])-1, m_min["mean"]),
            xytext=(0, 18), textcoords="offset points", ha="center", fontsize=9, color="#d73027", fontweight="bold")
plt.tight_layout()
plt.savefig("data/g_sazonal.png", dpi=150, bbox_inches="tight")
plt.close()

# Classes declividade
cores_d = ["#1a9850", "#a6d96a", "#fee08b", "#f46d43", "#d73027"]
labels_d = list(pct_decl.keys())
vals_d = list(pct_decl.values())

fig, ax = plt.subplots(figsize=(10, 3.5))
b = ax.barh(labels_d, vals_d, color=cores_d[:len(labels_d)], edgecolor="#2a2d37", height=0.6)
for bar, val in zip(b, vals_d):
    ax.text(bar.get_width() + 1, bar.get_y() + bar.get_height()/2,
            f"{val}%", va="center", fontsize=11, fontweight="bold", color="#e0e0e0")
ax.set_xlabel("% da Área do Sítio")
ax.invert_yaxis()
ax.grid(True, alpha=0.3, axis="x")
plt.tight_layout()
plt.savefig("data/g_declividade.png", dpi=150, bbox_inches="tight")
plt.close()

# Uso do solo
cores_u = ["#2166ac", "#d6604d", "#f4a582", "#92c5de", "#1b7837"]
labels_u = list(pct_uso.keys())
vals_u = list(pct_uso.values())

fig, ax = plt.subplots(figsize=(10, 3.5))
b = ax.barh(labels_u, vals_u, color=cores_u[:len(labels_u)], edgecolor="#2a2d37", height=0.6)
for bar, val in zip(b, vals_u):
    ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
            f"{val}%", va="center", fontsize=11, fontweight="bold", color="#e0e0e0")
ax.set_xlabel("% da Área do Sítio")
ax.invert_yaxis()
ax.grid(True, alpha=0.3, axis="x")
plt.tight_layout()
plt.savefig("data/g_uso_solo.png", dpi=150, bbox_inches="tight")
plt.close()

# ============================================================
# 4. MAPA INTERATIVO
# ============================================================
print("Montando mapa interativo...")
mapa = folium.Map(location=SITIO_CENTER, zoom_start=17, tiles=None, attr=" ")

camadas = [
    ("Satélite (Esri)", "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", "Esri"),
    ("Sentinel-2 (Cor Real)", tiles["rgb"], "ESA Copernicus"),
    ("Saúde da Vegetação (NDVI)", tiles["ndvi"], "ESA Copernicus"),
    ("Uso do Solo (ML)", tiles["uso"], "Classificação K-Means"),
    ("Elevação (metros)", tiles["elev"], "NASA SRTM"),
    ("Declividade (graus)", tiles["decl"], "NASA SRTM"),
    ("Aptidão Agrícola (EMBRAPA)", tiles["classes_decl"], "EMBRAPA"),
    ("Relevo 3D", tiles["hill"], "NASA SRTM"),
    ("Umidade do Terreno", tiles["twi"], "TWI"),
    ("Presença de Água (NDWI)", tiles["ndwi"], "ESA Copernicus"),
]

for nome, url, attr in camadas:
    folium.TileLayer(tiles=url, name=nome, attr=attr, overlay=False).add_to(mapa)

folium.GeoJson(gdf_sitio.to_json(), name="Limite do Sítio",
               style_function=lambda x: {"fillColor":"transparent","color":"#FFD700","weight":3,"fillOpacity":0}).add_to(mapa)
folium.CircleMarker(location=SITIO_CENTER, radius=6, color="#FFD700", fill=True,
                    fill_color="#228B22", fill_opacity=0.8).add_to(mapa)
folium.LayerControl().add_to(mapa)
mapa_html = mapa._repr_html_()

# ============================================================
# 5. CÁLCULOS DE INTERPRETAÇÃO
# ============================================================
ndvi_m = stats_ndvi["media"]
estado = "saudável" if ndvi_m >= 0.6 else "moderado" if ndvi_m >= 0.4 else "em alerta"
estado_cor = "#1a9850" if ndvi_m >= 0.6 else "#fdae61" if ndvi_m >= 0.4 else "#d73027"

ndvi_i = df_ndvi.head(10)["ndvi_medio"].mean()
ndvi_f = df_ndvi.tail(10)["ndvi_medio"].mean()
var_pct = ((ndvi_f - ndvi_i) / ndvi_i) * 100
if var_pct > 5: tend, tend_cor = f"+{var_pct:.1f}%", "#1a9850"
elif var_pct < -5: tend, tend_cor = f"{var_pct:.1f}%", "#d73027"
else: tend, tend_cor = f"{var_pct:+.1f}%", "#888"

mes_verde = meses_n[int(sazonal.loc[sazonal["mean"].idxmax(), "mes"])]
mes_seco = meses_n[int(sazonal.loc[sazonal["mean"].idxmin(), "mes"])]

# ============================================================
# 6. CONVERTER GRÁFICOS
# ============================================================
def b64(path):
    with open(path, "rb") as f: return base64.b64encode(f.read()).decode()

g = {k: b64(f"data/g_{k}.png") for k in ["serie", "sazonal", "declividade", "uso_solo"]}

# ============================================================
# 7. LEGENDAS POR CAMADA (JSON para JavaScript)
# ============================================================
import json
legendas = json.dumps({
    "Satélite (Esri)": [],
    "Sentinel-2 (Cor Real)": [],
    "Saúde da Vegetação (NDVI)": [
        {"cor": "#d73027", "txt": "Sem vegetação / construções"},
        {"cor": "#f46d43", "txt": "Solo exposto"},
        {"cor": "#fdae61", "txt": "Vegetação rala"},
        {"cor": "#fee08b", "txt": "Pastagem seca"},
        {"cor": "#d9ef8b", "txt": "Pastagem verde"},
        {"cor": "#66bd63", "txt": "Vegetação densa"},
        {"cor": "#1a9850", "txt": "Mata saudável"},
    ],
    "Uso do Solo (ML)": [
        {"cor": "#2166ac", "txt": "Água / sombra"},
        {"cor": "#d6604d", "txt": "Solo exposto / construções"},
        {"cor": "#f4a582", "txt": "Pastagem seca"},
        {"cor": "#92c5de", "txt": "Pastagem verde / cultivo"},
        {"cor": "#1b7837", "txt": "Mata"},
    ],
    "Elevação (metros)": [
        {"cor": "#313695", "txt": f"Baixo ({stats_elev['minimo']:.0f}m)"},
        {"cor": "#fee090", "txt": "Médio"},
        {"cor": "#a50026", "txt": f"Alto ({stats_elev['maximo']:.0f}m)"},
    ],
    "Declividade (graus)": [
        {"cor": "#1a9850", "txt": "Plano (0-5°)"},
        {"cor": "#fee08b", "txt": "Moderado (5-15°)"},
        {"cor": "#d73027", "txt": f"Íngreme (até {stats_decl['maximo']:.0f}°)"},
    ],
    "Aptidão Agrícola (EMBRAPA)": [
        {"cor": "#1a9850", "txt": "Plano — apto p/ mecanização"},
        {"cor": "#a6d96a", "txt": "Suave — mecanização restrita"},
        {"cor": "#fee08b", "txt": "Ondulado — pastagem"},
        {"cor": "#f46d43", "txt": "Forte — preservar"},
        {"cor": "#d73027", "txt": "Montanhoso — preservação obrigatória"},
    ],
    "Relevo 3D": [],
    "Umidade do Terreno": [
        {"cor": "#d73027", "txt": "Seco (topo/encosta)"},
        {"cor": "#fee08b", "txt": "Moderado"},
        {"cor": "#00441b", "txt": "Úmido (vale/baixada)"},
    ],
    "Presença de Água (NDWI)": [
        {"cor": "#d73027", "txt": "Seco"},
        {"cor": "#fee08b", "txt": "Pouca umidade"},
        {"cor": "#313695", "txt": "Água / muito úmido"},
    ],
})

# ============================================================
# 8. HTML FINAL
# ============================================================
print("Montando relatório final...")

html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GeoSítio — Relatório Completo</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:'Segoe UI',system-ui,sans-serif; background:#0f1117; color:#e0e0e0; line-height:1.7; }}
.hdr {{ background:linear-gradient(135deg,#1a3a2a 0%,#0f1117 100%); padding:50px 30px; text-align:center; border-bottom:3px solid #1a9850; }}
.hdr h1 {{ font-size:2.5em; color:#fff; letter-spacing:-0.5px; }}
.hdr .sub {{ color:#7a7a7a; margin-top:8px; font-size:1.1em; }}
.ctn {{ max-width:1300px; margin:0 auto; padding:30px 20px; }}

/* Métricas */
.mets {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:14px; margin-bottom:30px; }}
.met {{ background:#1a1d27; border-radius:14px; padding:22px 16px; text-align:center; border:1px solid #2a2d37; transition:transform .2s; }}
.met:hover {{ transform:translateY(-2px); border-color:#1a9850; }}
.met .v {{ font-size:1.8em; font-weight:700; color:#fff; }}
.met .l {{ font-size:.78em; color:#666; margin-top:4px; text-transform:uppercase; letter-spacing:1.2px; }}
.met .s {{ font-size:.75em; color:#555; margin-top:2px; }}

/* Seções */
.sec {{ background:#1a1d27; border-radius:14px; padding:32px; margin-bottom:24px; border:1px solid #2a2d37; }}
.sec h2 {{ color:#1a9850; font-size:1.5em; margin-bottom:6px; }}
.sec .exp {{ color:#888; font-size:.92em; margin-bottom:18px; padding-bottom:14px; border-bottom:1px solid #2a2d37; font-style:italic; }}
.sec p {{ color:#ccc; }}

/* Mapa */
.map-box {{ height:550px; border-radius:10px; overflow:hidden; margin:14px 0; border:1px solid #2a2d37; }}

/* Legenda dinâmica */
#legenda-dinamica {{ min-height:40px; display:flex; flex-wrap:wrap; gap:12px; align-items:center; padding:12px 0; }}
.leg-item {{ display:flex; align-items:center; gap:5px; font-size:.85em; color:#ccc; }}
.leg-cor {{ width:14px; height:14px; border-radius:3px; border:1px solid #3a3d47; }}

/* Gráficos */
.chart {{ text-align:center; margin:18px 0; }}
.chart img {{ max-width:100%; border-radius:10px; border:1px solid #2a2d37; }}

/* Insights */
.ins-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:14px; margin-top:16px; }}
.ins {{ background:#12141c; border-radius:10px; padding:22px; border-left:4px solid #1a9850; }}
.ins h3 {{ color:#fff; font-size:1em; margin-bottom:8px; }}
.ins p {{ font-size:.9em; color:#aaa; }}

/* Status badge */
.badge {{ display:inline-block; padding:3px 10px; border-radius:12px; font-weight:600; font-size:.85em; }}

/* Footer */
.ftr {{ text-align:center; padding:35px; color:#444; font-size:.82em; border-top:1px solid #1a1d27; margin-top:40px; }}
.ftr a {{ color:#1a9850; text-decoration:none; }}
</style>
</head>
<body>

<div class="hdr">
    <h1>GeoSítio — Monteiro Lobato</h1>
    <div class="sub">Relatório de Inteligência Geoespacial &nbsp;|&nbsp; Abril 2026</div>
</div>

<div class="ctn">

<!-- MÉTRICAS -->
<div class="mets">
    <div class="met"><div class="v">{area_m2/10_000:.2f} ha</div><div class="l">Área Total</div><div class="s">{area_m2:,.0f} m²</div></div>
    <div class="met"><div class="v">{perimetro_m:,.0f} m</div><div class="l">Perímetro</div></div>
    <div class="met"><div class="v" style="color:{estado_cor}">{stats_ndvi['media']:.2f}</div><div class="l">Vegetação (NDVI)</div><div class="s"><span class="badge" style="background:{estado_cor}22;color:{estado_cor}">{estado}</span></div></div>
    <div class="met"><div class="v" style="color:{tend_cor}">{tend}</div><div class="l">Tendência 3 anos</div></div>
    <div class="met"><div class="v">{stats_elev['minimo']:.0f}–{stats_elev['maximo']:.0f}m</div><div class="l">Elevação</div><div class="s">Desnível: {stats_elev['desnivel']:.0f}m</div></div>
    <div class="met"><div class="v">{stats_decl['media']:.1f}°</div><div class="l">Declividade Média</div></div>
    <div class="met"><div class="v">{qtd_imagens}</div><div class="l">Imagens de Satélite</div><div class="s">Sentinel-2 (último ano)</div></div>
    <div class="met"><div class="v">{len(df_ndvi)}</div><div class="l">Observações</div><div class="s">Série temporal (3 anos)</div></div>
</div>

<!-- MAPA -->
<div class="sec">
    <h2>Mapa Interativo da Propriedade</h2>
    <div class="exp">Use o seletor de camadas no canto superior direito do mapa para alternar entre as diferentes análises. A legenda abaixo muda automaticamente conforme a camada selecionada.</div>
    <div class="map-box">{mapa_html}</div>
    <div id="legenda-dinamica"><span style="color:#666;font-size:.9em;">Selecione uma camada no mapa para ver a legenda.</span></div>
</div>

<!-- USO DO SOLO -->
<div class="sec">
    <h2>O que tem em cada pedaço do sítio?</h2>
    <div class="exp">Usamos inteligência artificial (algoritmo K-Means) para analisar as imagens de satélite e separar automaticamente o sítio em 5 tipos de cobertura. Isso mostra onde tem mata, pasto, solo exposto e construções.</div>
    <div class="ins-grid">
        {"".join(f'<div class="ins" style="border-left-color:{c}"><h3>{l}</h3><p><strong>{v}%</strong> da área do sítio</p></div>' for l, v, c in zip(labels_u, vals_u, cores_u[:len(labels_u)]))}
    </div>
    <div class="chart"><img src="data:image/png;base64,{g['uso_solo']}" alt="Uso do solo"></div>
</div>

<!-- VEGETAÇÃO -->
<div class="sec">
    <h2>A vegetação está saudável?</h2>
    <div class="exp">O NDVI (Índice de Vegetação por Diferença Normalizada) é como um "exame de sangue" da vegetação, feito por satélite. Ele mede quanta luz infravermelha as plantas refletem — quanto mais saudável a planta, mais infravermelha ela reflete. Valores acima de 0.6 indicam vegetação saudável e densa.</div>
    <div class="ins-grid">
        <div class="ins">
            <h3>Estado atual</h3>
            <p>NDVI médio de <strong>{stats_ndvi['media']:.3f}</strong> — a vegetação está <strong style="color:{estado_cor}">{estado}</strong>.
            Varia de {stats_ndvi['minimo']:.2f} (construções/solo) até {stats_ndvi['maximo']:.2f} (mata densa).</p>
        </div>
        <div class="ins">
            <h3>Ao longo do ano</h3>
            <p>O sítio fica mais verde em <strong style="color:#1a9850">{mes_verde}</strong> (época de chuvas) e mais seco em <strong style="color:#d73027">{mes_seco}</strong> (seca do inverno). Padrão normal da Serra da Mantiqueira.</p>
        </div>
        <div class="ins">
            <h3>Tendência de 3 anos</h3>
            <p>A vegetação apresenta variação de <strong style="color:{tend_cor}">{tend}</strong> nos últimos 3 anos, baseado em {len(df_ndvi)} observações do satélite europeu Sentinel-2.</p>
        </div>
    </div>
</div>

<!-- SÉRIE TEMPORAL -->
<div class="sec">
    <h2>Como a vegetação mudou nos últimos 3 anos?</h2>
    <div class="exp">Cada ponto no gráfico é uma medição feita pelo satélite Sentinel-2 (da Agência Espacial Europeia). A linha verde mostra a tendência geral. As faixas coloridas indicam se a vegetação está saudável (verde), moderada (amarelo) ou em alerta (vermelho).</div>
    <div class="chart"><img src="data:image/png;base64,{g['serie']}" alt="Série temporal"></div>
</div>

<!-- SAZONAL -->
<div class="sec">
    <h2>Qual a época mais verde e mais seca?</h2>
    <div class="exp">Este gráfico mostra o ciclo anual da vegetação. As barras de erro indicam a variabilidade — quanto maiores, mais o valor muda de ano para ano naquele mês.</div>
    <div class="chart"><img src="data:image/png;base64,{g['sazonal']}" alt="Ciclo anual"></div>
</div>

<!-- RELEVO -->
<div class="sec">
    <h2>Como é o terreno do sítio?</h2>
    <div class="exp">Dados de radar da NASA (missão SRTM) com 30 metros de resolução. A declividade indica a inclinação do terreno — terrenos muito inclinados não servem pra mecanização e têm risco de erosão. A classificação da EMBRAPA (Empresa Brasileira de Pesquisa Agropecuária) define o que cada tipo de terreno aguenta.</div>
    <div class="ins-grid">
        <div class="ins">
            <h3>Altitude</h3>
            <p>O sítio vai de <strong>{stats_elev['minimo']:.0f}m</strong> a <strong>{stats_elev['maximo']:.0f}m</strong> de altitude (acima do nível do mar), com desnível de <strong>{stats_elev['desnivel']:.0f}m</strong>. Altitude típica da Serra da Mantiqueira.</p>
        </div>
        <div class="ins">
            <h3>Inclinação</h3>
            <p>Declividade média de <strong>{stats_decl['media']:.1f}°</strong>. O terreno é predominantemente ondulado — bom pra pastagem, mas exige cuidado com erosão nas áreas mais íngremes.</p>
        </div>
        <div class="ins" style="border-left-color:#f46d43">
            <h3>Onde pode mecanizar?</h3>
            <p>{pct_decl.get('Suave ondulado (3-8°)', 0)}% do sítio permite mecanização (com restrições). As áreas fortes ({pct_decl.get('Forte ondulado (20-45°)', 0)}%) devem ser preservadas ou usadas para pastagem extensiva.</p>
        </div>
    </div>
    <div class="chart"><img src="data:image/png;base64,{g['declividade']}" alt="Classes de declividade"></div>
</div>

<!-- ÁGUA -->
<div class="sec">
    <h2>Onde tem água e umidade?</h2>
    <div class="exp">Combinamos duas análises: o NDWI (índice de água por satélite) detecta água na superfície, e o TWI (índice de umidade topográfica) mostra onde o terreno naturalmente acumula água — vales e baixadas ficam mais úmidos, topos de morro ficam secos. Essas informações ajudam a decidir onde construir um tanque de peixes ou onde plantar culturas que precisam de mais água.</div>
    <div class="ins-grid">
        <div class="ins" style="border-left-color:#4575b4">
            <h3>Tanque de peixes</h3>
            <p>As melhores áreas para um tanque são onde o TWI é alto (acúmulo natural de água) e a declividade é baixa. Verifique no mapa as camadas "Umidade do Terreno" e "Declividade" juntas.</p>
        </div>
        <div class="ins" style="border-left-color:#4575b4">
            <h3>Fontes de água</h3>
            <p>O Ribeirão Sousas passa próximo ao sítio. Áreas com NDWI alto (azul no mapa "Presença de Água") podem indicar nascentes ou solo encharcado.</p>
        </div>
    </div>
</div>

<!-- RECOMENDAÇÕES -->
<div class="sec">
    <h2>Recomendações práticas</h2>
    <div class="exp">Com base nas análises de vegetação, relevo, uso do solo e água, estas são as recomendações para o sítio.</div>
    <div class="ins-grid">
        <div class="ins" style="border-left-color:#1a9850">
            <h3>Onde plantar</h3>
            <p>As áreas de declividade suave (até 8°) com boa vegetação são as mais indicadas para cultivo de frutas e hortaliças. Prefira as áreas mais baixas do terreno, onde há mais umidade natural.</p>
        </div>
        <div class="ins" style="border-left-color:#a6d96a">
            <h3>Onde deixar as vacas</h3>
            <p>As áreas classificadas como "pastagem" no mapa de uso do solo ({pct_uso.get('Vegetação rala (pastagem seca)', 0) + pct_uso.get('Vegetação moderada (pastagem/cultivo)', 0):.0f}% do sítio) são naturalmente indicadas. Evite as encostas mais íngremes para reduzir erosão.</p>
        </div>
        <div class="ins" style="border-left-color:#4575b4">
            <h3>Onde fazer um tanque</h3>
            <p>Busque no mapa a camada "Umidade do Terreno" — as áreas em verde escuro, combinadas com declividade baixa, são os melhores pontos. Proximidade ao Ribeirão Sousas facilita o abastecimento.</p>
        </div>
        <div class="ins" style="border-left-color:#f46d43">
            <h3>Onde preservar</h3>
            <p>As áreas de mata densa ({pct_uso.get('Vegetação densa (mata)', 0)}% do sítio) e encostas íngremes ({pct_decl.get('Forte ondulado (20-45°)', 0)}%) devem ser mantidas preservadas — protegem nascentes, evitam erosão e são exigência legal (Código Florestal).</p>
        </div>
    </div>
</div>

</div>

<div class="ftr">
    <p><strong>GeoSítio</strong> — Inteligência Geoespacial Aplicada à Propriedade Rural</p>
    <p>Dados: ESA Copernicus Sentinel-2 &nbsp;·&nbsp; NASA SRTM &nbsp;·&nbsp; Google Earth Engine &nbsp;·&nbsp; Python</p>
    <p style="margin-top:8px;">Projeto de portfólio em Ciência de Dados e IA</p>
</div>

<script>
// Legenda dinâmica que muda com a camada selecionada
const legendas = {legendas};
const legendaDiv = document.getElementById('legenda-dinamica');

function atualizarLegenda(nomeCamada) {{
    const items = legendas[nomeCamada];
    if (!items || items.length === 0) {{
        legendaDiv.innerHTML = '<span style="color:#666;font-size:.9em;">Esta camada não possui legenda específica.</span>';
        return;
    }}
    legendaDiv.innerHTML = '<span style="color:#aaa;font-weight:600;font-size:.9em;margin-right:8px;">' + nomeCamada + ':</span>' +
        items.map(i => '<div class="leg-item"><div class="leg-cor" style="background:' + i.cor + '"></div>' + i.txt + '</div>').join('');
}}

// Observar cliques nos radio buttons do LayerControl
setTimeout(() => {{
    const observer = new MutationObserver(() => {{
        document.querySelectorAll('.leaflet-control-layers-base label').forEach(label => {{
            const input = label.querySelector('input');
            const span = label.querySelector('span');
            if (input && span) {{
                input.addEventListener('change', () => {{
                    if (input.checked) atualizarLegenda(span.textContent.trim());
                }});
            }}
        }});
    }});
    const container = document.querySelector('.leaflet-control-layers');
    if (container) observer.observe(container, {{ childList: true, subtree: true }});

    // Também capturar cliques diretos
    document.addEventListener('click', (e) => {{
        const label = e.target.closest('.leaflet-control-layers-base label');
        if (label) {{
            const span = label.querySelector('span');
            if (span) setTimeout(() => atualizarLegenda(span.textContent.trim()), 100);
        }}
    }});

    // Legenda inicial
    atualizarLegenda('Satélite (Esri)');
}}, 1000);
</script>

</body>
</html>"""

Path("data/relatorio_final.html").write_text(html, encoding="utf-8")
print("\nRelatorio final salvo em data/relatorio_final.html")
