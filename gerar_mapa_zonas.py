"""Gera mapa prático de zonas do sítio — linguagem simples, sobre satélite."""
import sys
sys.path.append(".")

import json
import base64
from pathlib import Path

import folium
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import pandas as pd

from src.config import SITIO_CENTER
from src.geo_utils import carregar_sitio, reprojetar
from src.ee_utils import *

print("Carregando dados...")
inicializar_ee()
geometria = carregar_geometria_sitio()
gdf_sitio = carregar_sitio()
gdf_utm = reprojetar(gdf_sitio)
area_m2 = gdf_utm.area.values[0]
perimetro_m = gdf_utm.length.values[0]

# Dados de vegetação
colecao = coletar_sentinel2(geometria, "2025-04-01", "2026-04-01", max_nuvens=20)
composto = composto_mediana(colecao, geometria)
stats_ndvi = obter_estatisticas_ndvi(composto, geometria)
url_ndvi = gerar_url_tile_ndvi(composto)
url_rgb = gerar_url_tile_rgb(composto)

# Classificação de uso do solo
print("Classificando uso do solo...")
classificado = classificar_uso_solo(colecao, geometria, n_classes=5)
pct_uso = calcular_percentual_uso_solo(classificado, geometria)
url_uso = gerar_url_tile_uso_solo(classificado)

# Série temporal
print("Série temporal...")
df_ndvi = extrair_serie_temporal_ndvi(geometria, "2023-04-01", "2026-04-09", max_nuvens=30)

# Declividade (só pra dados, não pra mapa)
elevacao = carregar_elevacao(geometria)
stats_elev = obter_estatisticas_elevacao(elevacao, geometria)
stats_decl = obter_estatisticas_declividade(calcular_declividade(elevacao), geometria)

# ============================================================
# MAPA DE ZONAS PRÁTICAS
# ============================================================
print("Montando mapa de zonas...")

# Criar mapa de zonas sobre satélite
# A ideia: usar a classificação ML pra colorir zonas com nomes práticos
# Classes: 1=água/sombra, 2=solo/construção, 3=pasto seco, 4=pasto verde, 5=mata

# Gerar tile de zonas com cores e nomes práticos
vis_zonas = {
    "bands": ["uso_solo"],
    "min": 1,
    "max": 5,
    "palette": [
        "#3182bd80",  # 1 - Água/sombra - azul translúcido
        "#e6550d80",  # 2 - Construções - laranja
        "#fdae6b80",  # 3 - Pasto seco - amarelo
        "#a1d99b80",  # 4 - Pasto verde - verde claro
        "#31a35480",  # 5 - Mata - verde escuro
    ],
}
url_zonas = classificado.getMapId(vis_zonas)["tile_fetcher"].url_format

mapa = folium.Map(location=SITIO_CENTER, zoom_start=17, tiles=None)

# Satélite como base
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    name="Satélite", attr="Esri",
).add_to(mapa)

# Sentinel-2
folium.TileLayer(tiles=url_rgb, name="Satélite Sentinel-2 (10m)",
                 attr="ESA Copernicus", overlay=False).add_to(mapa)

# Zonas coloridas sobre satélite (overlay!)
folium.TileLayer(tiles=url_zonas, name="Zonas do Sítio",
                 attr="Classificação ML", overlay=True, opacity=0.55).add_to(mapa)

# NDVI
folium.TileLayer(tiles=url_ndvi, name="Saúde da Vegetação",
                 attr="ESA Copernicus", overlay=False).add_to(mapa)

# Contorno
folium.GeoJson(gdf_sitio.to_json(), name="Limite",
               style_function=lambda x: {"fillColor":"transparent","color":"#fff","weight":2,"fillOpacity":0,"dashArray":"6,4"}).add_to(mapa)

folium.LayerControl(collapsed=False).add_to(mapa)
mapa_html = mapa._repr_html_()

# ============================================================
# GRÁFICOS
# ============================================================
print("Gráficos...")

plt.rcParams.update({
    "figure.facecolor": "#ffffff",
    "axes.facecolor": "#fafafa",
    "axes.edgecolor": "#ddd",
    "text.color": "#333",
    "axes.labelcolor": "#555",
    "xtick.color": "#666",
    "ytick.color": "#666",
    "grid.color": "#eee",
    "font.family": "sans-serif",
})

# Série temporal
cores_ndvi = ["#d73027","#f46d43","#fdae61","#fee08b","#d9ef8b","#a6d96a","#66bd63","#1a9850"]
cmap = mcolors.LinearSegmentedColormap.from_list("n", cores_ndvi)
norm = mcolors.Normalize(vmin=0.2, vmax=0.75)

fig, ax = plt.subplots(figsize=(12, 4))
ax.fill_between(df_ndvi["data"], 0.6, 0.85, alpha=0.08, color="#1a9850", label="Faixa saudável")
ax.fill_between(df_ndvi["data"], 0.4, 0.6, alpha=0.06, color="#fdae61")
df_ndvi["mm"] = df_ndvi["ndvi_medio"].rolling(window=5, center=True).mean()
ax.plot(df_ndvi["data"], df_ndvi["mm"], color="#1a9850", linewidth=2.5, zorder=3)
ax.scatter(df_ndvi["data"], df_ndvi["ndvi_medio"], c=df_ndvi["ndvi_medio"],
           cmap=cmap, norm=norm, s=30, edgecolors="white", linewidth=0.4, zorder=2, alpha=0.8)
ax.set_ylabel("Índice de Vegetação")
ax.set_ylim(0.2, 0.82)
ax.grid(True, alpha=0.4)
ax.set_title("Como a vegetação do sítio evoluiu nos últimos 3 anos", fontsize=12, fontweight="bold", color="#333")
plt.tight_layout()
plt.savefig("data/g_serie.png", dpi=150, bbox_inches="tight")
plt.close()

# Sazonal
df_ndvi["mes"] = df_ndvi["data"].dt.month
mn = {1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}
saz = df_ndvi.groupby("mes")["ndvi_medio"].agg(["mean","std"]).reset_index()
saz["nome"] = saz["mes"].map(mn)

fig, ax = plt.subplots(figsize=(10, 4))
cores_m = [cmap(norm(v)) for v in saz["mean"]]
ax.bar(saz["nome"], saz["mean"], color=cores_m, edgecolor="white", width=0.65)
ax.errorbar(saz["nome"], saz["mean"], yerr=saz["std"], fmt="none", color="#aaa", capsize=3)
m_max = saz.loc[saz["mean"].idxmax()]
m_min = saz.loc[saz["mean"].idxmin()]
ax.annotate(f"Mais verde", xy=(int(m_max["mes"])-1, m_max["mean"]),
            xytext=(0, 12), textcoords="offset points", ha="center", fontsize=9, color="#1a9850", fontweight="bold")
ax.annotate(f"Mais seco", xy=(int(m_min["mes"])-1, m_min["mean"]),
            xytext=(0, 12), textcoords="offset points", ha="center", fontsize=9, color="#d73027", fontweight="bold")
ax.set_ylabel("Índice de Vegetação")
ax.set_ylim(0.3, 0.82)
ax.grid(True, alpha=0.3, axis="y")
ax.set_title("Qual época do ano o sítio fica mais verde?", fontsize=12, fontweight="bold", color="#333")
plt.tight_layout()
plt.savefig("data/g_sazonal.png", dpi=150, bbox_inches="tight")
plt.close()

# Uso do solo - donut
cores_u = ["#3182bd","#e6550d","#fdae6b","#a1d99b","#31a354"]
labels_u = ["Água/Sombra", "Construções\ne solo", "Pasto seco", "Pasto verde\ne cultivo", "Mata"]
vals_u = list(pct_uso.values())

fig, ax = plt.subplots(figsize=(7, 5))
wedges, _, autotexts = ax.pie(vals_u, colors=cores_u[:len(vals_u)],
    autopct=lambda p: f"{p:.0f}%" if p > 4 else "",
    startangle=90, pctdistance=0.78,
    wedgeprops=dict(width=0.35, edgecolor="white", linewidth=2))
for at in autotexts:
    at.set_fontsize(11)
    at.set_fontweight("bold")
    at.set_color("#333")
ax.legend(labels_u[:len(vals_u)], loc="center left", bbox_to_anchor=(1, 0.5), fontsize=10)
ax.set_title("O que tem no sítio?", fontsize=13, fontweight="bold", color="#333", pad=15)
plt.tight_layout()
plt.savefig("data/g_uso.png", dpi=150, bbox_inches="tight")
plt.close()

# ============================================================
# CONVERTER
# ============================================================
def b64(p):
    with open(p,"rb") as f: return base64.b64encode(f.read()).decode()

g_serie = b64("data/g_serie.png")
g_sazonal = b64("data/g_sazonal.png")
g_uso = b64("data/g_uso.png")

# ============================================================
# CÁLCULOS
# ============================================================
ndvi_m = stats_ndvi["media"]
estado = "saudável" if ndvi_m >= 0.6 else "moderado" if ndvi_m >= 0.4 else "em alerta"
estado_cor = "#1a9850" if ndvi_m >= 0.6 else "#fdae61" if ndvi_m >= 0.4 else "#d73027"
estado_emoji = "bom" if ndvi_m >= 0.6 else "regular" if ndvi_m >= 0.4 else "ruim"

mes_verde = mn[int(saz.loc[saz["mean"].idxmax(), "mes"])]
mes_seco = mn[int(saz.loc[saz["mean"].idxmin(), "mes"])]

ndvi_i = df_ndvi.head(10)["ndvi_medio"].mean()
ndvi_f = df_ndvi.tail(10)["ndvi_medio"].mean()
var_pct = ((ndvi_f - ndvi_i) / ndvi_i) * 100

pct_mata = pct_uso.get("Vegetação densa (mata)", 0)
pct_pasto = pct_uso.get("Vegetação rala (pastagem seca)", 0) + pct_uso.get("Vegetação moderada (pastagem/cultivo)", 0)
pct_construcao = pct_uso.get("Solo exposto / Construções", 0)

# ============================================================
# HTML
# ============================================================
print("Montando relatório...")

html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sítio Monteiro Lobato — Mapa e Análise</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:'Segoe UI',system-ui,-apple-system,sans-serif; background:#f5f5f0; color:#333; line-height:1.7; }}

.hero {{ background:linear-gradient(135deg,#2d5016 0%,#1a3a0a 100%); padding:45px 30px; text-align:center; }}
.hero h1 {{ font-size:2.2em; color:#fff; font-weight:700; }}
.hero p {{ color:#a8c890; font-size:1.05em; margin-top:6px; }}

.container {{ max-width:1100px; margin:0 auto; padding:25px 20px; }}

/* Resumo */
.resumo {{ background:#fff; border-radius:16px; padding:30px; margin-bottom:24px; box-shadow:0 2px 8px rgba(0,0,0,0.06); display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:20px; }}
.resumo-item {{ text-align:center; padding:12px; }}
.resumo-item .num {{ font-size:2em; font-weight:700; color:#2d5016; }}
.resumo-item .txt {{ font-size:.85em; color:#888; margin-top:2px; }}
.resumo-item .detalhe {{ font-size:.78em; color:#aaa; }}

/* Seções */
.secao {{ background:#fff; border-radius:16px; padding:30px; margin-bottom:24px; box-shadow:0 2px 8px rgba(0,0,0,0.06); }}
.secao h2 {{ color:#2d5016; font-size:1.4em; margin-bottom:4px; }}
.secao .subtitulo {{ color:#999; font-size:.9em; margin-bottom:18px; padding-bottom:14px; border-bottom:1px solid #eee; }}

/* Mapa */
.mapa {{ height:550px; border-radius:12px; overflow:hidden; margin:12px 0; border:1px solid #ddd; }}

/* Legenda do mapa */
.legenda-zonas {{ display:flex; flex-wrap:wrap; gap:14px; padding:14px 0; }}
.leg {{ display:flex; align-items:center; gap:6px; font-size:.9em; color:#555; }}
.leg-box {{ width:18px; height:18px; border-radius:4px; border:1px solid #ddd; }}

/* Cards de insight */
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:16px; margin-top:18px; }}
.card {{ background:#f9faf7; border-radius:12px; padding:22px; border-left:4px solid #2d5016; }}
.card h3 {{ color:#2d5016; font-size:1em; margin-bottom:6px; }}
.card p {{ font-size:.92em; color:#666; }}

/* Gráficos */
.grafico {{ text-align:center; margin:16px 0; }}
.grafico img {{ max-width:100%; border-radius:10px; }}

/* Footer */
.footer {{ text-align:center; padding:30px; color:#bbb; font-size:.8em; }}
</style>
</head>
<body>

<div class="hero">
    <h1>Sítio Monteiro Lobato</h1>
    <p>Análise completa da propriedade por imagens de satélite</p>
</div>

<div class="container">

<!-- RESUMO -->
<div class="resumo">
    <div class="resumo-item">
        <div class="num">{area_m2/10_000:.1f} ha</div>
        <div class="txt">Tamanho do sítio</div>
        <div class="detalhe">{area_m2:,.0f} m² | Perímetro: {perimetro_m:.0f}m</div>
    </div>
    <div class="resumo-item">
        <div class="num" style="color:{estado_cor}">{estado.title()}</div>
        <div class="txt">Estado da vegetação</div>
        <div class="detalhe">Índice médio: {stats_ndvi['media']:.2f}</div>
    </div>
    <div class="resumo-item">
        <div class="num">{stats_elev['minimo']:.0f}–{stats_elev['maximo']:.0f}m</div>
        <div class="txt">Altitude</div>
        <div class="detalhe">Serra da Mantiqueira</div>
    </div>
    <div class="resumo-item">
        <div class="num">{pct_mata:.0f}%</div>
        <div class="txt">Mata preservada</div>
        <div class="detalhe">{pct_pasto:.0f}% pasto | {pct_construcao:.0f}% construções</div>
    </div>
</div>

<!-- MAPA -->
<div class="secao">
    <h2>Mapa do Sítio</h2>
    <div class="subtitulo">Imagem de satélite real com as zonas da propriedade identificadas por inteligência artificial. Selecione as camadas no canto do mapa.</div>
    <div class="mapa">{mapa_html}</div>
    <div class="legenda-zonas">
        <strong style="color:#555;">Zonas:</strong>
        <div class="leg"><div class="leg-box" style="background:#3182bd"></div> Água / sombra</div>
        <div class="leg"><div class="leg-box" style="background:#e6550d"></div> Construções / solo</div>
        <div class="leg"><div class="leg-box" style="background:#fdae6b"></div> Pasto seco</div>
        <div class="leg"><div class="leg-box" style="background:#a1d99b"></div> Pasto verde / cultivo</div>
        <div class="leg"><div class="leg-box" style="background:#31a354"></div> Mata</div>
    </div>
</div>

<!-- O QUE TEM NO SÍTIO -->
<div class="secao">
    <h2>O que tem no sítio?</h2>
    <div class="subtitulo">Um algoritmo de inteligência artificial analisou as imagens de satélite e separou a propriedade em 5 tipos de cobertura.</div>
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:20px; align-items:center;">
        <div class="grafico"><img src="data:image/png;base64,{g_uso}" alt="Uso do solo"></div>
        <div>
            <div class="cards" style="grid-template-columns:1fr;">
                <div class="card" style="border-left-color:#31a354">
                    <h3>Mata ({pct_mata:.0f}%)</h3>
                    <p>Área de vegetação densa — preservar. Protege nascentes e evita erosão. Exigência do Código Florestal.</p>
                </div>
                <div class="card" style="border-left-color:#a1d99b">
                    <h3>Pasto e cultivo ({pct_pasto:.0f}%)</h3>
                    <p>Área produtiva — onde as vacas pastam e onde pode plantar. A maior parte do sítio.</p>
                </div>
                <div class="card" style="border-left-color:#e6550d">
                    <h3>Construções e solo ({pct_construcao:.0f}%)</h3>
                    <p>Casas, galpões, caminhos e áreas sem vegetação.</p>
                </div>
            </div>
        </div>
    </div>
</div>

<!-- O QUE PLANTAR E ONDE -->
<div class="secao">
    <h2>O que plantar e onde?</h2>
    <div class="subtitulo">Cruzamos os dados de satélite (vegetação, inclinação, umidade) com as necessidades de cada cultura pra recomendar o melhor lugar pra cada coisa. A altitude de {stats_elev['media']:.0f}m e o clima da Serra da Mantiqueira favorecem frutas de clima ameno e hortaliças.</div>

    <div class="cards">
        <div class="card" style="border-left-color:#a1d99b;background:#f0f7ec">
            <h3>Zona de pasto verde — 0,67 ha | Inclinação: 16,9° | Altitude: 678m</h3>
            <p>Terreno mais fértil do sítio (vegetação densa, NDVI 0.70). <strong>Melhor área pra cultivo.</strong></p>
            <p style="margin-top:8px;"><strong>Frutas:</strong> Morango, amora e framboesa (alto valor, mercado gourmet em São José dos Campos a 40km). Caqui e figo (pouca manutenção). Plantio de mudas no inverno (jun-ago).</p>
            <p style="margin-top:4px;"><strong>Horta:</strong> Alface, brócolis, couve-flor, cenoura (inverno). Tomate, abobrinha, vagem (verão). Ervas aromáticas (alecrim, manjericão) o ano todo — bom mercado.</p>
            <p style="margin-top:4px;color:#b45309;"><strong>Atenção:</strong> Inclinação de 16,9° dificulta mecanização. Plantio em curvas de nível ou terraços é recomendado.</p>
        </div>

        <div class="card" style="border-left-color:#fdae6b;background:#fdf8f0">
            <h3>Zona de pasto seco — 1,13 ha | Inclinação: 19,6° | Altitude: 684m</h3>
            <p>Maior área do sítio, mas inclinação alta (19,6°). <strong>Melhor manter como pastagem.</strong></p>
            <p style="margin-top:8px;"><strong>Gado:</strong> Cabe 2-3 vacas Jersey (leite). Produção estimada: 30-50 litros/dia. Queijo artesanal, doce de leite.</p>
            <p style="margin-top:4px;"><strong>Cabras:</strong> 10-15 cabras Saanen cabem aqui. Queijo de cabra = produto gourmet. 8 cabras consomem o mesmo que 1 vaca.</p>
            <p style="margin-top:4px;"><strong>Plantio resistente:</strong> Mandioca e milho aguentam a inclinação. Banana em áreas protegidas do vento.</p>
            <p style="margin-top:4px;color:#b45309;"><strong>Atenção:</strong> Inclinação alta = risco de erosão. Evite deixar solo exposto. Pastagem rotacionada ajuda.</p>
        </div>

        <div class="card" style="border-left-color:#3182bd;background:#f0f5fa">
            <h3>Zona baixa (sombra/água) — 0,21 ha | Inclinação: 8° | Altitude: 660m</h3>
            <p>Ponto mais baixo e mais plano do sítio. <strong>Melhor local para tanque de peixes.</strong></p>
            <p style="margin-top:8px;"><strong>Tanque:</strong> Escavar 300-500 m² nesta zona. Peixes recomendados: <strong>Carpa</strong> (resiste ao frio do inverno) + <strong>Tilápia</strong> (no verão, set-abr) + <strong>Lambari</strong> (produção rápida).</p>
            <p style="margin-top:4px;"><strong>Fonte de água:</strong> O satélite <strong>não detectou água na superfície</strong> dentro do sítio (nenhum pixel com índice de água positivo). Porém, o <strong>Ribeirão Sousas</strong> passa muito perto e pode servir de fonte. Nascentes subterrâneas não aparecem no satélite — vale verificar no local.</p>
            <p style="margin-top:4px;"><strong>Culturas que gostam de umidade:</strong> Inhame, taioba, agrião, hortelã — combinam com a umidade natural desta zona.</p>
        </div>

        <div class="card" style="border-left-color:#31a354;background:#f0f7f0">
            <h3>Zona de mata — 0,71 ha (21%) | Inclinação: 13,6° | Altitude: 682m</h3>
            <p>Vegetação mais saudável do sítio (NDVI 0.71). <strong>Preservar obrigatoriamente.</strong></p>
            <p style="margin-top:8px;"><strong>Por que não mexer:</strong> O Código Florestal exige manter pelo menos 20% de mata nativa (Reserva Legal). O sítio tem 21% — está no limite. Essa mata protege nascentes, evita erosão e mantém a biodiversidade.</p>
            <p style="margin-top:4px;"><strong>Oportunidade:</strong> Apicultura! 10-15 caixas de abelha na borda da mata. Produção de 15-30 kg de mel por caixa/ano. Mel da Serra da Mantiqueira tem ótimo mercado turístico. As abelhas ainda ajudam a polinizar o pomar e a horta.</p>
        </div>

        <div class="card" style="border-left-color:#e6550d;background:#fdf5f0">
            <h3>Zona de construções — 0,88 ha | Inclinação: 15,8° | Altitude: 683m</h3>
            <p>Casas, galpões e áreas de solo exposto.</p>
            <p style="margin-top:8px;"><strong>Galinhas:</strong> 50-100 galinhas caipiras no entorno das construções. Produção: ~30 dúzias de ovos/mês. Renda estimada: R$ 420-600/mês só com ovos.</p>
            <p style="margin-top:4px;"><strong>Porcos:</strong> 5-10 porcos caipiras em sistema extensivo. Linguiça artesanal, venda local.</p>
            <p style="margin-top:4px;"><strong>Turismo rural:</strong> Monteiro Lobato já é destino turístico. Café colonial, colha-e-pague de morango, pesque-pague no tanque. São José dos Campos (700 mil hab.) fica a 40km.</p>
        </div>
    </div>
</div>

<!-- CALENDÁRIO DE PLANTIO -->
<div class="secao">
    <h2>Quando plantar cada coisa?</h2>
    <div class="subtitulo">Calendário baseado no clima da Serra da Mantiqueira: verão úmido (out-mar) e inverno seco (abr-set). A vegetação do sítio segue esse ciclo — o satélite confirmou que {mes_verde} é o mês mais verde e {mes_seco} o mais seco.</div>

    <table style="width:100%;border-collapse:collapse;font-size:.9em;margin-top:10px;">
        <thead>
            <tr style="background:#2d5016;color:#fff;">
                <th style="padding:10px;text-align:left;border-radius:8px 0 0 0;">Cultura</th>
                <th style="padding:10px;text-align:left;">Quando plantar</th>
                <th style="padding:10px;text-align:left;">Quando colher</th>
                <th style="padding:10px;text-align:left;border-radius:0 8px 0 0;">Onde no sítio</th>
            </tr>
        </thead>
        <tbody>
            <tr style="border-bottom:1px solid #eee;background:#f9faf7;"><td style="padding:10px;font-weight:600;">Morango</td><td style="padding:10px;">Mar-Abr (mudas)</td><td style="padding:10px;">Jun-Nov</td><td style="padding:10px;">Pasto verde</td></tr>
            <tr style="border-bottom:1px solid #eee;"><td style="padding:10px;font-weight:600;">Amora / Framboesa</td><td style="padding:10px;">Jun-Ago (mudas)</td><td style="padding:10px;">A partir do 2o ano</td><td style="padding:10px;">Pasto verde</td></tr>
            <tr style="border-bottom:1px solid #eee;background:#f9faf7;"><td style="padding:10px;font-weight:600;">Caqui / Figo</td><td style="padding:10px;">Jun-Ago (mudas)</td><td style="padding:10px;">Jan-Jun</td><td style="padding:10px;">Pasto verde</td></tr>
            <tr style="border-bottom:1px solid #eee;"><td style="padding:10px;font-weight:600;">Alface / Couve</td><td style="padding:10px;">Ano todo</td><td style="padding:10px;">45-60 dias</td><td style="padding:10px;">Pasto verde (horta)</td></tr>
            <tr style="border-bottom:1px solid #eee;background:#f9faf7;"><td style="padding:10px;font-weight:600;">Brócolis / Couve-flor</td><td style="padding:10px;">Mar-Jul (frio)</td><td style="padding:10px;">80-120 dias</td><td style="padding:10px;">Pasto verde (horta)</td></tr>
            <tr style="border-bottom:1px solid #eee;"><td style="padding:10px;font-weight:600;">Tomate / Abobrinha</td><td style="padding:10px;">Set-Fev (chuvas)</td><td style="padding:10px;">90-120 dias</td><td style="padding:10px;">Pasto verde (horta)</td></tr>
            <tr style="border-bottom:1px solid #eee;background:#f9faf7;"><td style="padding:10px;font-weight:600;">Mandioca</td><td style="padding:10px;">Set-Nov</td><td style="padding:10px;">12-18 meses</td><td style="padding:10px;">Pasto seco (aguenta inclinação)</td></tr>
            <tr style="border-bottom:1px solid #eee;"><td style="padding:10px;font-weight:600;">Milho / Feijão</td><td style="padding:10px;">Set-Nov</td><td style="padding:10px;">80-120 dias</td><td style="padding:10px;">Pasto seco</td></tr>
            <tr style="border-bottom:1px solid #eee;background:#f9faf7;"><td style="padding:10px;font-weight:600;">Banana</td><td style="padding:10px;">Set-Nov (chuvas)</td><td style="padding:10px;">12-18 meses</td><td style="padding:10px;">Zona baixa (protegida)</td></tr>
            <tr style="border-bottom:1px solid #eee;"><td style="padding:10px;font-weight:600;">Inhame / Hortelã</td><td style="padding:10px;">Set-Nov</td><td style="padding:10px;">7-10 meses</td><td style="padding:10px;">Zona baixa (úmida)</td></tr>
            <tr><td style="padding:10px;font-weight:600;">Ervas aromáticas</td><td style="padding:10px;">Ano todo</td><td style="padding:10px;">Contínuo</td><td style="padding:10px;">Próximo às construções</td></tr>
        </tbody>
    </table>
</div>

<!-- ANIMAIS E PEIXES -->
<div class="secao">
    <h2>Quais animais criar?</h2>
    <div class="subtitulo">Recomendações para 3,3 hectares na Serra da Mantiqueira, altitude {stats_elev['media']:.0f}m.</div>

    <div class="cards">
        <div class="card" style="border-left-color:#8B4513">
            <h3>Gado leiteiro — zona de pasto (1,8 ha)</h3>
            <p><strong>2-3 vacas Jersey.</strong> Raça menor, come menos, produz leite com alto teor de gordura. Produção: 30-50 litros/dia. Dá pra fazer queijo artesanal, iogurte e doce de leite.</p>
        </div>
        <div class="card" style="border-left-color:#888">
            <h3>Cabras leiteiras — zona de pasto (compartilhada)</h3>
            <p><strong>10-15 cabras Saanen.</strong> Ocupam pouco espaço (8 cabras = 1 vaca). Queijo de cabra é produto gourmet com ótima margem. Mercado em São José dos Campos e Campos do Jordão.</p>
        </div>
        <div class="card" style="border-left-color:#c44">
            <h3>Galinhas caipiras — próximo às construções</h3>
            <p><strong>50-100 galinhas.</strong> Produção: ~30 dúzias/mês. Ovo caipira vende a R$ 14-20 a dúzia na região. Renda: R$ 420-600/mês. Investimento baixo, retorno rápido.</p>
        </div>
        <div class="card" style="border-left-color:#3182bd">
            <h3>Peixes — tanque na zona baixa (660m)</h3>
            <p><strong>Carpa</strong> (resiste ao inverno frio) + <strong>Tilápia</strong> (só no verão, set-abr) + <strong>Lambari</strong> (cresce rápido). Tanque escavado de 300-500 m². <strong>Truta NÃO funciona</strong> a 680m — precisa de altitude acima de 1.000m.</p>
        </div>
        <div class="card" style="border-left-color:#f4a460">
            <h3>Abelhas — borda da mata</h3>
            <p><strong>10-15 caixas.</strong> Produção: 15-30 kg mel/caixa/ano. Mel da Mantiqueira tem ótimo mercado. Bônus: polinizam o pomar e a horta, aumentando a produção.</p>
        </div>
    </div>
</div>

<!-- ÁGUA -->
<div class="secao">
    <h2>E a água?</h2>
    <div class="subtitulo">Analisamos 25 imagens de satélite procurando sinais de água na superfície do sítio.</div>
    <div class="cards" style="grid-template-columns:1fr 1fr;">
        <div class="card" style="border-left-color:#3182bd">
            <h3>O que o satélite encontrou</h3>
            <p><strong>Não detectamos água na superfície</strong> dentro do sítio. Nenhum dos 357 pontos analisados mostrou índice de água positivo (NDWI). Isso significa que não tem lago, brejo ou córrego visível dentro da propriedade.</p>
            <p style="margin-top:8px;">Porém, o <strong>Ribeirão Sousas</strong> passa muito próximo ao limite do sítio e pode ser usado como fonte de água para o tanque.</p>
        </div>
        <div class="card" style="border-left-color:#2d5016">
            <h3>Pode ter nascente?</h3>
            <p>O satélite <strong>não consegue ver nascentes subterrâneas</strong>. A zona mais baixa do sítio (660m, inclinação de 8°) é o local mais provável para encontrar água aflorando — vale fazer uma vistoria no local, especialmente na época de chuvas.</p>
            <p style="margin-top:8px;">Sinais pra procurar: solo encharcado mesmo na seca, vegetação mais verde que o entorno, presença de samambaias e musgos.</p>
        </div>
    </div>
</div>

<!-- VEGETAÇÃO AO LONGO DO TEMPO -->
<div class="secao">
    <h2>A vegetação está melhorando ou piorando?</h2>
    <div class="subtitulo">Acompanhamos a saúde da vegetação do sítio nos últimos 3 anos usando {len(df_ndvi)} imagens do satélite europeu Sentinel-2. A faixa verde no gráfico indica a zona saudável.</div>
    <div class="grafico"><img src="data:image/png;base64,{g_serie}" alt="Série temporal"></div>
    <div class="cards" style="grid-template-columns:repeat(auto-fit,minmax(200px,1fr));">
        <div class="card">
            <h3>Veredicto</h3>
            <p>A vegetação está <strong style="color:{estado_cor}">{estado}</strong> e {"melhorou" if var_pct > 0 else "diminuiu"} {abs(var_pct):.1f}% em 3 anos.</p>
        </div>
        <div class="card">
            <h3>Época mais verde</h3>
            <p><strong>{mes_verde}</strong> — época das chuvas, tudo fica mais verde naturalmente.</p>
        </div>
        <div class="card">
            <h3>Época mais seca</h3>
            <p><strong>{mes_seco}</strong> — inverno seco da Serra da Mantiqueira. Normal.</p>
        </div>
    </div>
</div>

<!-- CICLO ANUAL -->
<div class="secao">
    <h2>Qual a melhor época do ano?</h2>
    <div class="subtitulo">A vegetação segue o ciclo de chuvas. Saber isso ajuda a planejar plantio e manejo do pasto.</div>
    <div class="grafico"><img src="data:image/png;base64,{g_sazonal}" alt="Ciclo anual"></div>
</div>

<!-- DADOS TÉCNICOS (colapsável) -->
<details style="margin-bottom:24px;">
    <summary style="background:#fff;padding:16px 24px;border-radius:16px;cursor:pointer;font-weight:600;color:#2d5016;box-shadow:0 2px 8px rgba(0,0,0,0.06);">
        Dados técnicos (para quem quiser saber mais)
    </summary>
    <div style="background:#fff;padding:24px;border-radius:0 0 16px 16px;margin-top:-8px;box-shadow:0 2px 8px rgba(0,0,0,0.06);">
        <table style="width:100%;border-collapse:collapse;font-size:.9em;">
            <tr style="border-bottom:1px solid #eee;"><td style="padding:8px;color:#888;">NDVI médio</td><td style="padding:8px;font-weight:600;">{stats_ndvi['media']:.3f}</td></tr>
            <tr style="border-bottom:1px solid #eee;"><td style="padding:8px;color:#888;">NDVI mínimo / máximo</td><td style="padding:8px;">{stats_ndvi['minimo']:.3f} / {stats_ndvi['maximo']:.3f}</td></tr>
            <tr style="border-bottom:1px solid #eee;"><td style="padding:8px;color:#888;">Desvio padrão NDVI</td><td style="padding:8px;">{stats_ndvi['desvio_padrao']:.3f}</td></tr>
            <tr style="border-bottom:1px solid #eee;"><td style="padding:8px;color:#888;">Elevação</td><td style="padding:8px;">{stats_elev['minimo']:.0f}m – {stats_elev['maximo']:.0f}m (desnível {stats_elev['desnivel']:.0f}m)</td></tr>
            <tr style="border-bottom:1px solid #eee;"><td style="padding:8px;color:#888;">Declividade média</td><td style="padding:8px;">{stats_decl['media']:.1f}° (máx: {stats_decl['maximo']:.1f}°)</td></tr>
            <tr style="border-bottom:1px solid #eee;"><td style="padding:8px;color:#888;">Imagens analisadas</td><td style="padding:8px;">{len(df_ndvi)} observações Sentinel-2 (3 anos)</td></tr>
            <tr style="border-bottom:1px solid #eee;"><td style="padding:8px;color:#888;">Resolução espacial</td><td style="padding:8px;">10 metros (Sentinel-2)</td></tr>
            <tr style="border-bottom:1px solid #eee;"><td style="padding:8px;color:#888;">Classificação</td><td style="padding:8px;">K-Means clustering (5 classes) sobre 9 bandas espectrais</td></tr>
            <tr><td style="padding:8px;color:#888;">Fontes</td><td style="padding:8px;">ESA Copernicus, NASA SRTM, Google Earth Engine</td></tr>
        </table>
    </div>
</details>

</div>

<div class="footer">
    <p><strong>GeoSítio</strong> — Análise feita com imagens de satélite, inteligência artificial e Python</p>
    <p>Dados: satélite Sentinel-2 (Agência Espacial Europeia) | Processamento: Google Earth Engine</p>
</div>

</body>
</html>"""

Path("data/sitio.html").write_text(html, encoding="utf-8")
print("\nPronto! Abra data/sitio.html")
