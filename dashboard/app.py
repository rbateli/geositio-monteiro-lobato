"""GeoSítio — Dashboard de Inteligência Geoespacial."""
import sys
sys.path.append(".")

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import folium
from streamlit_folium import st_folium
import pandas as pd

from src.config import SITIO_CENTER
from src.geo_utils import carregar_sitio, reprojetar
from src.ee_utils import *

# ============================================================
# CONFIG
# ============================================================
st.set_page_config(
    page_title="GeoSítio — Monteiro Lobato",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# CSS customizado
st.markdown("""
<style>
    /* Layout geral */
    .block-container { padding-top: 1.5rem; max-width: 1100px; }
    header[data-testid="stHeader"] { background: #fafaf5; }

    /* Tipografia */
    h1 { color: #2d5016 !important; font-weight: 700 !important; letter-spacing: -0.5px !important; }
    h2 { color: #2d5016 !important; font-weight: 600 !important; margin-top: 1.5rem !important; }
    h3 { color: #3a6b1e !important; font-weight: 600 !important; }

    /* Métricas */
    div[data-testid="stMetric"] {
        background: #fff;
        border-radius: 14px;
        padding: 18px 16px;
        border: 1px solid #e5e8df;
        box-shadow: 0 1px 4px rgba(0,0,0,0.04);
    }
    div[data-testid="stMetric"] label { color: #777 !important; font-size: 0.82em !important; text-transform: uppercase; letter-spacing: 0.5px; }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] { font-size: 1.6em !important; color: #2d5016 !important; }

    /* Tabs */
    button[data-baseweb="tab"] { font-weight: 600 !important; font-size: 0.92em !important; }
    button[data-baseweb="tab"][aria-selected="true"] { color: #2d5016 !important; }

    /* Expander */
    div[data-testid="stExpander"] { background: #fff; border-radius: 14px; border: 1px solid #e5e8df; }

    /* Radio horizontal */
    div[data-testid="stRadio"] > div { gap: 0.3rem !important; }
    div[data-testid="stRadio"] label { background: #fff !important; border: 1px solid #e5e8df !important; border-radius: 8px !important; padding: 6px 14px !important; font-size: 0.88em !important; }
    div[data-testid="stRadio"] label[data-checked="true"] { background: #2d5016 !important; color: #fff !important; border-color: #2d5016 !important; }

    /* Divider */
    hr { border-color: #e8ebe2 !important; margin: 1.5rem 0 !important; }

    /* Alerts */
    div[data-testid="stAlert"] { border-radius: 10px !important; }

    /* Tables */
    table { font-size: 0.9em !important; }
    thead tr th { background: #f0f2eb !important; color: #2d5016 !important; font-weight: 600 !important; }
</style>
""", unsafe_allow_html=True)


# ============================================================
# CACHE DE DADOS
# ============================================================
@st.cache_data(ttl=3600, show_spinner="Carregando dados de satélite...")
def carregar_todos_dados():
    inicializar_ee()
    geometria = carregar_geometria_sitio()
    gdf = carregar_sitio()
    gdf_utm = reprojetar(gdf)
    area_m2 = gdf_utm.area.values[0]
    perimetro_m = gdf_utm.length.values[0]

    # Sentinel-2
    colecao = coletar_sentinel2(geometria, "2025-04-01", "2026-04-01", max_nuvens=20)
    qtd_imgs = colecao.size().getInfo()
    composto = composto_mediana(colecao, geometria)
    stats_ndvi = obter_estatisticas_ndvi(composto, geometria)

    # Série temporal
    df_ndvi = extrair_serie_temporal_ndvi(geometria, "2023-04-01", "2026-04-09", max_nuvens=30)

    # Relevo
    elevacao = carregar_elevacao(geometria)
    stats_elev = obter_estatisticas_elevacao(elevacao, geometria)
    stats_decl = obter_estatisticas_declividade(calcular_declividade(elevacao), geometria)

    # Classificação
    classificado = classificar_uso_solo(colecao, geometria, n_classes=5)
    pct_uso = calcular_percentual_uso_solo(classificado, geometria)

    # Tiles
    url_rgb = gerar_url_tile_rgb(composto)
    url_ndvi = gerar_url_tile_ndvi(composto)
    url_uso = gerar_url_tile_uso_solo(classificado)

    return {
        "area_m2": area_m2, "perimetro_m": perimetro_m,
        "stats_ndvi": stats_ndvi, "stats_elev": stats_elev, "stats_decl": stats_decl,
        "df_ndvi": df_ndvi, "pct_uso": pct_uso, "qtd_imgs": qtd_imgs,
        "url_rgb": url_rgb, "url_ndvi": url_ndvi, "url_uso": url_uso,
        "gdf": gdf,
    }


dados = carregar_todos_dados()

# Variáveis
area_m2 = dados["area_m2"]
perimetro_m = dados["perimetro_m"]
stats_ndvi = dados["stats_ndvi"]
stats_elev = dados["stats_elev"]
stats_decl = dados["stats_decl"]
df_ndvi = dados["df_ndvi"]
pct_uso = dados["pct_uso"]
gdf_sitio = dados["gdf"]

ndvi_m = stats_ndvi["media"]
estado = "Saudável" if ndvi_m >= 0.6 else "Moderado" if ndvi_m >= 0.4 else "Em alerta"
estado_delta = "normal" if ndvi_m >= 0.6 else "off" if ndvi_m >= 0.4 else "inverse"

pct_mata = pct_uso.get("Vegetação densa (mata)", 0)
pct_pasto_seco = pct_uso.get("Vegetação rala (pastagem seca)", 0)
pct_pasto_verde = pct_uso.get("Vegetação moderada (pastagem/cultivo)", 0)
pct_construcao = pct_uso.get("Solo exposto / Construções", 0)
pct_agua = pct_uso.get("Água / Sombra", 0)
pct_pasto = pct_pasto_seco + pct_pasto_verde

ndvi_i = df_ndvi.head(10)["ndvi_medio"].mean()
ndvi_f = df_ndvi.tail(10)["ndvi_medio"].mean()
var_pct = ((ndvi_f - ndvi_i) / ndvi_i) * 100

df_ndvi["mes"] = df_ndvi["data"].dt.month
mn = {1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}
saz = df_ndvi.groupby("mes")["ndvi_medio"].agg(["mean","std","count"]).reset_index()
saz["nome"] = saz["mes"].map(mn)
mes_verde = mn[int(saz.loc[saz["mean"].idxmax(), "mes"])]
mes_seco = mn[int(saz.loc[saz["mean"].idxmin(), "mes"])]


# ============================================================
# HEADER
# ============================================================
st.markdown("""
<div style="background:linear-gradient(135deg,#2d5016,#4a7c28);padding:30px 35px;border-radius:16px;margin-bottom:20px;">
    <h1 style="color:#fff !important;margin:0;font-size:2em;">Sitio Monteiro Lobato</h1>
    <p style="color:#c8e0b0;margin:6px 0 0 0;font-size:1.05em;">Analise completa da propriedade por imagens de satelite e inteligencia artificial</p>
</div>
""", unsafe_allow_html=True)

# ============================================================
# MÉTRICAS
# ============================================================
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Área", f"{area_m2/10_000:.1f} ha", f"{area_m2:,.0f} m²")
c2.metric("Perímetro", f"{perimetro_m:.0f} m")
c3.metric("Vegetação", f"{ndvi_m:.2f}", estado, delta_color=estado_delta)
c4.metric("Tendência 3 anos", f"{var_pct:+.1f}%")
c5.metric("Altitude", f"{stats_elev['minimo']:.0f}–{stats_elev['maximo']:.0f}m", f"Desnível {stats_elev['desnivel']:.0f}m")
c6.metric("Declividade", f"{stats_decl['media']:.1f}°", f"Máx {stats_decl['maximo']:.1f}°")

st.divider()

# ============================================================
# MAPA
# ============================================================
st.header("Mapa do Sítio")

camada = st.radio(
    "Escolha a camada:",
    ["Satélite", "Sentinel-2 (10m)", "Saúde da Vegetação (NDVI)", "Uso do Solo (IA)"],
    horizontal=True,
)

mapa = folium.Map(location=SITIO_CENTER, zoom_start=17, tiles=None)

folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    name="Satélite", attr="Esri",
).add_to(mapa)

url_map = {
    "Satélite": None,
    "Sentinel-2 (10m)": dados["url_rgb"],
    "Saúde da Vegetação (NDVI)": dados["url_ndvi"],
    "Uso do Solo (IA)": dados["url_uso"],
}

if url_map[camada]:
    folium.TileLayer(tiles=url_map[camada], name=camada, attr="GEE/ESA", overlay=True, opacity=0.85).add_to(mapa)

folium.GeoJson(gdf_sitio.to_json(), name="Limite",
               style_function=lambda x: {"fillColor":"transparent","color":"#FFD700","weight":2.5,"fillOpacity":0,"dashArray":"6,4"}).add_to(mapa)

st_folium(mapa, width="100%", height=500)

# Legenda contextual
if camada == "Saúde da Vegetação (NDVI)":
    cols = st.columns(7)
    leg = [("#d73027","Sem vegetação"), ("#f46d43","Solo exposto"), ("#fdae61","Ralo"),
           ("#fee08b","Pasto seco"), ("#d9ef8b","Pasto verde"), ("#66bd63","Vegetação densa"), ("#1a9850","Mata")]
    for c, (cor, txt) in zip(cols, leg):
        c.markdown(f'<div style="text-align:center"><div style="width:100%;height:12px;background:{cor};border-radius:4px;margin-bottom:4px;"></div><span style="font-size:.75em;color:#888;">{txt}</span></div>', unsafe_allow_html=True)
elif camada == "Uso do Solo (IA)":
    cols = st.columns(5)
    leg = [("#2166ac","Água/Sombra"), ("#d6604d","Construções"), ("#f4a582","Pasto seco"), ("#92c5de","Pasto verde"), ("#1b7837","Mata")]
    for c, (cor, txt) in zip(cols, leg):
        c.markdown(f'<div style="text-align:center"><div style="width:100%;height:12px;background:{cor};border-radius:4px;margin-bottom:4px;"></div><span style="font-size:.75em;color:#888;">{txt}</span></div>', unsafe_allow_html=True)

st.divider()

# ============================================================
# O QUE TEM NO SÍTIO
# ============================================================
st.header("O que tem no sítio?")
st.caption("Inteligência artificial analisou as imagens de satélite e classificou cada parte da propriedade.")

col_chart, col_detail = st.columns([1, 1])

with col_chart:
    nomes_uso = ["Água/Sombra", "Construções", "Pasto seco", "Pasto verde", "Mata"]
    valores_uso = [pct_agua, pct_construcao, pct_pasto_seco, pct_pasto_verde, pct_mata]
    cores_uso = ["#2166ac", "#d6604d", "#f4a582", "#a1d99b", "#1b7837"]

    fig = go.Figure(go.Pie(
        labels=nomes_uso, values=valores_uso,
        hole=0.45, marker_colors=cores_uso,
        textinfo="percent+label", textposition="outside",
        textfont_size=13,
        pull=[0, 0, 0, 0, 0.05],
    ))
    fig.update_layout(
        showlegend=False, height=380, margin=dict(t=20, b=20, l=20, r=20),
        font=dict(family="Segoe UI"),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, width="stretch")

with col_detail:
    st.markdown(f"""
    | Zona | Área | O que é |
    |------|------|---------|
    | 🌳 **Mata** | {pct_mata:.0f}% (0.71 ha) | Vegetação densa — preservar (obrigatório por lei) |
    | 🟢 **Pasto verde** | {pct_pasto_verde:.0f}% (0.67 ha) | Área mais fértil — melhor pra cultivo |
    | 🟡 **Pasto seco** | {pct_pasto_seco:.0f}% (1.13 ha) | Maior área — pastagem pra gado e cabras |
    | 🏠 **Construções** | {pct_construcao:.0f}% (0.88 ha) | Casas, galpões e solo exposto |
    | 💧 **Água/Sombra** | {pct_agua:.0f}% (0.21 ha) | Zona baixa — melhor local pro tanque |
    """)

st.divider()

# ============================================================
# O QUE PLANTAR E ONDE
# ============================================================
st.header("O que plantar e onde?")
st.caption("Cruzamos dados de vegetação, inclinação e umidade com as necessidades de cada cultura.")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🟢 Pasto verde (cultivo)",
    "🟡 Pasto seco (pastagem)",
    "💧 Zona baixa (tanque)",
    "🌳 Mata (preservar)",
    "🏠 Construções",
])

with tab1:
    st.subheader("Zona de pasto verde — 0,67 ha")
    c1, c2, c3 = st.columns(3)
    c1.metric("Inclinação", "16,9°", "moderada")
    c2.metric("Altitude", "678 m")
    c3.metric("Vegetação (NDVI)", "0.70", "densa")
    st.success("**Melhor área pra cultivo.** Terreno mais fértil do sítio.")
    st.markdown("#### Frutas recomendadas")
    st.markdown("""
    | Fruta | Por que funciona aqui | Quando plantar | Quando colher |
    |-------|----------------------|----------------|---------------|
    | **Morango** | Clima ameno ideal; já cultivado na Mantiqueira | Mudas em Mar-Abr | Jun-Nov |
    | **Amora** | Ótima adaptação a 600-800m | Mudas Jun-Ago | A partir do 2° ano |
    | **Framboesa** | Alto valor; mercado gourmet | Mudas Jun-Ago | A partir do 2° ano |
    | **Caqui** | Pouca manutenção; produz bem | Mudas Jun-Ago | Jan-Jun |
    | **Figo** | Rústico; boa produção | Mudas Jun-Ago | Jan-Mar |
    """)
    st.markdown("#### Horta")
    st.markdown("""
    | Cultura | Época | Ciclo | Observação |
    |---------|-------|-------|------------|
    | **Alface / Couve** | Ano todo | 45-60 dias | Favorecida pelo clima ameno |
    | **Brócolis / Couve-flor** | Mar-Jul (frio) | 80-120 dias | Menos pragas na altitude |
    | **Cenoura / Beterraba** | Mar-Jul | 60-110 dias | Muito boa em altitude |
    | **Tomate / Abobrinha** | Set-Fev (chuvas) | 90-120 dias | Boa renda |
    | **Ervas aromáticas** | Ano todo | Contínuo | Alecrim, manjericão — bom mercado em SJC (40km) |
    """)
    st.warning("**Atenção:** Inclinação de 16,9° dificulta mecanização. Recomenda-se plantio em curvas de nível ou terraços.")

with tab2:
    st.subheader("Zona de pasto seco — 1,13 ha")
    c1, c2, c3 = st.columns(3)
    c1.metric("Inclinação", "19,6°", "alta")
    c2.metric("Altitude", "684 m")
    c3.metric("Vegetação (NDVI)", "0.62", "moderada")
    st.info("**Maior área do sítio.** Inclinação alta — melhor manter como pastagem.")
    st.markdown("""
    | Uso | Recomendação | Detalhe |
    |-----|-------------|---------|
    | **Gado** | 2-3 vacas Jersey | Leite: 30-50 L/dia. Queijo, doce de leite |
    | **Cabras** | 10-15 cabras Saanen | Queijo de cabra gourmet. 8 cabras = 1 vaca |
    | **Mandioca** | Aguenta inclinação | Plantio Set-Nov, colheita 12-18 meses |
    | **Milho / Feijão** | Alimento + ração | Plantio Set-Nov, colheita 80-120 dias |
    | **Banana** | Em áreas protegidas | Precisa de proteção contra vento e frio |
    """)
    st.error("**Risco de erosão** em encostas de 19,6°. Evitar solo exposto. Pastagem rotacionada ajuda.")

with tab3:
    st.subheader("Zona baixa — 0,21 ha")
    c1, c2, c3 = st.columns(3)
    c1.metric("Inclinação", "8°", "suave")
    c2.metric("Altitude", "660 m", "ponto mais baixo")
    c3.metric("Água detectada", "Não", "0 pixels positivos")
    st.info("**Ponto mais baixo e plano do sítio.** Melhor local para tanque de peixes.")
    st.markdown("#### Peixes recomendados")
    st.markdown("""
    | Peixe | Funciona? | Por quê |
    |-------|----------|---------|
    | **Carpa** | ✅ SIM | Resiste ao frio do inverno. Melhor opção. |
    | **Tilápia** | ⚠️ SÓ VERÃO | Só de Set a Abr. Morre abaixo de 10°C. |
    | **Lambari** | ✅ SIM | Cresce rápido (3 meses). Resistente. |
    | **Truta** | ❌ NÃO | Precisa de altitude >1.000m. Não funciona a 680m. |
    """)
    st.markdown("**Tanque:** Escavar 300-500 m² nesta zona. Profundidade 1,2-1,5m.")
    st.markdown("#### Fonte de água")
    st.warning("O satélite **não detectou água** na superfície dentro do sítio (nenhum dos 357 pontos analisados). Porém, o **Ribeirão Sousas** passa muito perto e pode servir de fonte. Nascentes subterrâneas não aparecem no satélite — vale verificar no local (procurar solo encharcado, samambaias e musgos).")
    st.markdown("#### Culturas que gostam de umidade")
    st.markdown("Inhame, taioba, agrião, hortelã — combinam com a umidade natural desta zona.")

with tab4:
    st.subheader("Zona de mata — 0,71 ha (21%)")
    c1, c2, c3 = st.columns(3)
    c1.metric("Inclinação", "13,6°")
    c2.metric("Altitude", "682 m")
    c3.metric("Vegetação (NDVI)", "0.71", "mais saudável")
    st.success("**Preservar obrigatoriamente.** O Código Florestal exige 20% de mata nativa — o sítio tem 21%, no limite.")
    st.markdown("""
    - **Protege nascentes** e evita erosão nas encostas
    - **Biodiversidade** — fauna e flora nativos da Mata Atlântica
    - **Apicultura na borda:** 10-15 caixas de abelha. Mel da Mantiqueira tem ótimo mercado turístico
    - As abelhas **polinizam o pomar e a horta**, aumentando a produção (15-30 kg mel/caixa/ano)
    """)

with tab5:
    st.subheader("Zona de construções — 0,88 ha")
    c1, c2, c3 = st.columns(3)
    c1.metric("Inclinação", "15,8°")
    c2.metric("Altitude", "683 m")
    c3.metric("Vegetação (NDVI)", "0.55", "baixa (construções)")
    st.markdown("""
    | Atividade | Detalhe | Renda estimada |
    |-----------|---------|---------------|
    | **Galinhas caipiras** | 50-100 aves. Ovo caipira: R$14-20/dúzia | R$ 420-600/mês |
    | **Porcos caipiras** | 5-10 porcos. Linguiça artesanal | Consumo + venda local |
    | **Turismo rural** | Café colonial, colha-e-pague, pesque-pague | Variável |
    """)
    st.info("**Monteiro Lobato já é destino turístico.** São José dos Campos (700 mil hab.) fica a 40km. Oportunidade: café da manhã colonial com produção própria (ovos, queijo, mel, geleia).")

st.divider()

# ============================================================
# VEGETAÇÃO AO LONGO DO TEMPO
# ============================================================
st.header("A vegetação está melhorando ou piorando?")
st.caption(f"Acompanhamos a saúde do sítio nos últimos 3 anos com {len(df_ndvi)} imagens do satélite europeu Sentinel-2.")

# Série temporal com Plotly
df_ndvi["mm"] = df_ndvi["ndvi_medio"].rolling(window=5, center=True).mean()

fig = go.Figure()

# Faixas de referência
fig.add_hrect(y0=0.6, y1=0.85, fillcolor="#1a9850", opacity=0.07, line_width=0, annotation_text="Saudável", annotation_position="right")
fig.add_hrect(y0=0.4, y1=0.6, fillcolor="#fdae61", opacity=0.05, line_width=0, annotation_text="Moderado", annotation_position="right")
fig.add_hrect(y0=0.15, y1=0.4, fillcolor="#d73027", opacity=0.04, line_width=0, annotation_text="Alerta", annotation_position="right")

# Pontos
fig.add_trace(go.Scatter(
    x=df_ndvi["data"], y=df_ndvi["ndvi_medio"],
    mode="markers", name="Medição",
    marker=dict(size=7, color=df_ndvi["ndvi_medio"], colorscale="RdYlGn", cmin=0.2, cmax=0.75,
                line=dict(width=0.5, color="white")),
    hovertemplate="Data: %{x|%d/%m/%Y}<br>NDVI: %{y:.3f}<extra></extra>",
))

# Tendência
fig.add_trace(go.Scatter(
    x=df_ndvi["data"], y=df_ndvi["mm"],
    mode="lines", name="Tendência",
    line=dict(color="#1a9850", width=3),
))

fig.update_layout(
    height=400, margin=dict(t=10, b=40, l=50, r=50),
    yaxis=dict(title="Indice de Vegetacao (NDVI)", range=[0.15, 0.85], gridcolor="#eee"),
    xaxis=dict(title="", gridcolor="#eee"),
    legend=dict(orientation="h", yanchor="top", y=-0.12),
    font=dict(family="Segoe UI"),
    hovermode="x unified",
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#fff",
)
st.plotly_chart(fig, width="stretch")

# Cards
c1, c2, c3 = st.columns(3)
c1.metric("Veredicto", estado, f"{var_pct:+.1f}% em 3 anos")
c2.metric("Época mais verde", mes_verde, "Chuvas")
c3.metric("Época mais seca", mes_seco, "Inverno seco")

st.divider()

# ============================================================
# CICLO ANUAL
# ============================================================
st.header("Qual a melhor época do ano?")
st.caption("A vegetação segue o ciclo de chuvas. Saber isso ajuda a planejar plantio e manejo.")

fig = go.Figure()

fig.add_trace(go.Bar(
    x=saz["nome"], y=saz["mean"],
    marker_color=[px.colors.sample_colorscale("RdYlGn", [(v - 0.3) / 0.5])[0] for v in saz["mean"]],
    error_y=dict(type="data", array=saz["std"], color="#aaa", thickness=1.5),
    hovertemplate="Mês: %{x}<br>NDVI médio: %{y:.3f}<extra></extra>",
    text=[f"{v:.2f}" for v in saz["mean"]],
    textposition="outside",
    textfont=dict(size=11),
))

fig.update_layout(
    height=380, margin=dict(t=10, b=40, l=50, r=20),
    yaxis=dict(title="Indice de Vegetacao (NDVI)", range=[0.3, 0.85], gridcolor="#eee"),
    xaxis=dict(gridcolor="#eee"),
    font=dict(family="Segoe UI"),
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#fff",
)
st.plotly_chart(fig, width="stretch")

st.divider()

# ============================================================
# ANIMAIS
# ============================================================
st.header("Quais animais criar?")
st.caption(f"Recomendacoes para {area_m2/10_000:.1f} hectares na Serra da Mantiqueira, altitude {stats_elev['media']:.0f}m.")

def card_animal(emoji, titulo, qtd, onde, detalhes, renda=""):
    renda_html = f'<div style="background:#e8f5e0;color:#2d5016;padding:6px 10px;border-radius:6px;font-weight:600;font-size:.85em;margin-top:8px;">{renda}</div>' if renda else ""
    return f"""
    <div style="background:#fff;border-radius:14px;padding:22px;border:1px solid #e5e8df;box-shadow:0 1px 4px rgba(0,0,0,0.04);height:100%;">
        <div style="font-size:2em;margin-bottom:4px;">{emoji}</div>
        <div style="font-weight:700;font-size:1.05em;color:#2d5016;margin-bottom:4px;">{titulo}</div>
        <div style="font-weight:600;color:#333;margin-bottom:2px;">{qtd}</div>
        <div style="font-size:.82em;color:#888;margin-bottom:8px;">{onde}</div>
        <div style="font-size:.9em;color:#555;line-height:1.6;">{detalhes}</div>
        {renda_html}
    </div>"""

c1, c2, c3 = st.columns(3)
c1.markdown(card_animal("🐄", "Gado leiteiro", "2-3 vacas Jersey", "Zona de pasto (1,8 ha)",
    "Raca menor, come menos. Leite com alto teor de gordura. Producao: 30-50 litros/dia. Queijo artesanal, doce de leite."), unsafe_allow_html=True)
c2.markdown(card_animal("🐐", "Cabras leiteiras", "10-15 cabras Saanen", "Pasto compartilhado",
    "8 cabras consomem o mesmo que 1 vaca. Queijo de cabra gourmet. Mercado em SJC e Campos do Jordao.", "Excelente margem no queijo fino"), unsafe_allow_html=True)
c3.markdown(card_animal("🐔", "Galinhas caipiras", "50-100 galinhas", "Proximo as construcoes",
    "~30 duzias de ovos/mes. Ovo caipira: R$14-20/duzia. Investimento baixo, retorno rapido.", "Renda: R$420-600/mes"), unsafe_allow_html=True)

st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

c1, c2 = st.columns(2)
c1.markdown(card_animal("🐟", "Peixes", "Carpa + Tilapia + Lambari", "Tanque na zona baixa (660m)",
    "Carpa resiste ao frio do inverno. Tilapia so no verao (set-abr). Lambari cresce rapido. Tanque: 300-500 m2. <strong>Truta NAO funciona</strong> a 680m."), unsafe_allow_html=True)
c2.markdown(card_animal("🐝", "Abelhas", "10-15 caixas", "Borda da mata",
    "Mel da Mantiqueira = otimo mercado turistico. 15-30 kg/caixa/ano. Bonus: polinizam pomar e horta, aumentando producao."), unsafe_allow_html=True)

st.divider()

# ============================================================
# DADOS TÉCNICOS
# ============================================================
with st.expander("📊 Dados técnicos (para quem quiser saber mais)"):
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Vegetação")
        st.markdown(f"""
        | Indicador | Valor |
        |-----------|-------|
        | NDVI médio | {stats_ndvi['media']:.3f} |
        | NDVI mínimo | {stats_ndvi['minimo']:.3f} |
        | NDVI máximo | {stats_ndvi['maximo']:.3f} |
        | Desvio padrão | {stats_ndvi['desvio_padrao']:.3f} |
        | Imagens analisadas | {dados['qtd_imgs']} (último ano) |
        | Série temporal | {len(df_ndvi)} observações (3 anos) |
        """)
    with c2:
        st.markdown("#### Terreno")
        st.markdown(f"""
        | Indicador | Valor |
        |-----------|-------|
        | Elevação mín / máx | {stats_elev['minimo']:.0f}m / {stats_elev['maximo']:.0f}m |
        | Desnível | {stats_elev['desnivel']:.0f}m |
        | Declividade média | {stats_decl['media']:.1f}° |
        | Declividade máxima | {stats_decl['maximo']:.1f}° |
        | Resolução (satélite) | 10m (Sentinel-2) |
        | Resolução (terreno) | 30m (SRTM) |
        """)

    st.markdown("**Fontes:** ESA Copernicus Sentinel-2 · NASA SRTM · Google Earth Engine · EMBRAPA · IBGE")

# ============================================================
# FOOTER
# ============================================================
st.divider()
st.markdown("""
<div style="text-align:center;padding:20px 10px;">
    <div style="font-weight:700;color:#2d5016;font-size:1em;margin-bottom:4px;">GeoSitio</div>
    <div style="color:#aaa;font-size:.82em;">Inteligencia Geoespacial Aplicada a Propriedade Rural</div>
    <div style="color:#ccc;font-size:.78em;margin-top:4px;">Sentinel-2 (ESA) &middot; SRTM (NASA) &middot; Google Earth Engine &middot; Python</div>
</div>
""", unsafe_allow_html=True)
