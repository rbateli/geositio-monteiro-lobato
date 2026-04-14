"""Gera site final do GeoSítio — HTML puro com Plotly.js + Leaflet."""
import sys
sys.path.append(".")

import json
from pathlib import Path

import plotly.graph_objects as go
import plotly.express as px
import plotly.io as pio
import folium
import pandas as pd

from src.config import SITIO_CENTER
from src.geo_utils import carregar_sitio, reprojetar
from src.ee_utils import *

# ============================================================
# DADOS
# ============================================================
print("[1/5] Earth Engine...")
inicializar_ee()
geometria = carregar_geometria_sitio()
gdf = carregar_sitio()
gdf_utm = reprojetar(gdf)
area_m2 = gdf_utm.area.values[0]
perimetro_m = gdf_utm.length.values[0]

print("[2/5] Sentinel-2 + NDVI...")
colecao = coletar_sentinel2(geometria, "2025-04-01", "2026-04-01", max_nuvens=20)
qtd = colecao.size().getInfo()
composto = composto_mediana(colecao, geometria)
sn = obter_estatisticas_ndvi(composto, geometria)
url_rgb = gerar_url_tile_rgb(composto)
url_ndvi = gerar_url_tile_ndvi(composto)

print("[3/5] Serie temporal...")
df = extrair_serie_temporal_ndvi(geometria, "2023-04-01", "2026-04-09", max_nuvens=30)

print("[4/5] Relevo...")
elev = carregar_elevacao(geometria)
se = obter_estatisticas_elevacao(elev, geometria)
sd = obter_estatisticas_declividade(calcular_declividade(elev), geometria)

print("[5/5] Classificacao...")
cls = classificar_uso_solo(colecao, geometria, n_classes=5)
pu = calcular_percentual_uso_solo(cls, geometria)
url_uso = gerar_url_tile_uso_solo(cls)

# Calculos
ndvi_m = sn["media"]
estado = "Saudavel" if ndvi_m >= 0.6 else "Moderado" if ndvi_m >= 0.4 else "Em alerta"
estado_cor = "#16a34a" if ndvi_m >= 0.6 else "#eab308" if ndvi_m >= 0.4 else "#dc2626"
ni, nf = df.head(10)["ndvi_medio"].mean(), df.tail(10)["ndvi_medio"].mean()
var = ((nf - ni) / ni) * 100
df["mes"] = df["data"].dt.month
mn = {1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}
saz = df.groupby("mes")["ndvi_medio"].agg(["mean","std"]).reset_index()
saz["nome"] = saz["mes"].map(mn)
mv = mn[int(saz.loc[saz["mean"].idxmax(), "mes"])]
ms = mn[int(saz.loc[saz["mean"].idxmin(), "mes"])]

pm = pu.get("Vegetacao densa (mata)", pu.get("Vegetação densa (mata)", 0))
pps = pu.get("Vegetacao rala (pastagem seca)", pu.get("Vegetação rala (pastagem seca)", 0))
ppv = pu.get("Vegetacao moderada (pastagem/cultivo)", pu.get("Vegetação moderada (pastagem/cultivo)", 0))
pc = pu.get("Solo exposto / Construcoes", pu.get("Solo exposto / Construções", 0))
pa = pu.get("Agua / Sombra", pu.get("Água / Sombra", 0))
pp = pps + ppv

# ============================================================
# GRAFICOS PLOTLY (exportados como div HTML)
# ============================================================
print("Graficos...")

# Paleta — Refined Minimalism Dashboard (v2)
DS = {
    "ink":       "#09090B",  # zinc-950 near-black
    "ink_2":     "#3F3F46",  # zinc-700
    "muted":     "#71717A",  # zinc-500
    "bg":        "#FAFAFA",  # zinc-50
    "surface":   "#FFFFFF",
    "border":    "#E4E4E7",  # zinc-200
    "accent":    "#65A30D",  # lime-600 — único destaque vibrante
    "accent_2":  "#0EA5E9",  # sky-500 — secundário
    "warn":      "#EAB308",  # yellow-500
    "danger":    "#DC2626",  # red-600
    "data": ["#09090B", "#65A30D", "#0EA5E9", "#EAB308", "#DC2626", "#8B5CF6", "#71717A", "#3F6212"],
}

FONT_SANS = "Geist, ui-sans-serif, system-ui, sans-serif"
FONT_MONO = "'Geist Mono', ui-monospace, 'SF Mono', Menlo, monospace"

plotly_config = dict(displayModeBar=False, responsive=True)
layout_base = dict(
    font=dict(family=FONT_SANS, color=DS["ink_2"], size=12),
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(t=16, b=44, l=52, r=24),
    colorway=DS["data"],
    hoverlabel=dict(bgcolor=DS["ink"], bordercolor=DS["ink"],
                    font=dict(family=FONT_MONO, color="#FFFFFF", size=11)),
)

# Série temporal NDVI
df["mm"] = df["ndvi_medio"].rolling(window=5, center=True).mean()
fig1 = go.Figure()
fig1.add_hrect(y0=0.6, y1=0.85, fillcolor=DS["accent"], opacity=0.06, line_width=0)
fig1.add_trace(go.Scatter(
    x=df["data"], y=df["ndvi_medio"], mode="markers", name="Medição",
    marker=dict(size=5, color=DS["muted"], opacity=0.45, line=dict(width=0)),
    hovertemplate="%{x|%d %b %Y}<br><b>%{y:.3f}</b><extra></extra>",
))
fig1.add_trace(go.Scatter(
    x=df["data"], y=df["mm"], mode="lines", name="Tendência",
    line=dict(color=DS["ink"], width=2.5, shape="spline", smoothing=0.6),
    hovertemplate="Tendência<br><b>%{y:.3f}</b><extra></extra>",
))
fig1.update_layout(
    **layout_base, height=360,
    yaxis=dict(title="", range=[0.2, 0.82], gridcolor=DS["border"],
               zeroline=False, tickfont=dict(color=DS["muted"], size=11),
               showline=False),
    xaxis=dict(gridcolor="rgba(0,0,0,0)", zeroline=False,
               tickfont=dict(color=DS["muted"], size=11), showline=False),
    legend=dict(orientation="h", y=-0.18, x=0, font=dict(size=12, color=DS["ink_2"])),
    hovermode="x unified",
)
chart_serie = pio.to_html(fig1, full_html=False, config=plotly_config)

# Sazonal
cores_saz = [DS["accent"] if v >= 0.6 else (DS["warn"] if v >= 0.5 else DS["muted"]) for v in saz["mean"]]
fig2 = go.Figure()
fig2.add_trace(go.Bar(
    x=saz["nome"], y=saz["mean"], marker=dict(color=cores_saz, line=dict(width=0)),
    error_y=dict(type="data", array=saz["std"], color=DS["border"], thickness=1, width=4),
    text=[f"{v:.2f}" for v in saz["mean"]], textposition="outside",
    textfont=dict(size=11, color=DS["ink"], family=FONT_MONO),
    hovertemplate="<b>%{x}</b><br>NDVI %{y:.3f}<extra></extra>",
    cliponaxis=False,
))
fig2.update_layout(
    **layout_base, height=320,
    yaxis=dict(title="", range=[0.35, 0.85], gridcolor=DS["border"],
               zeroline=False, tickfont=dict(color=DS["muted"], size=11), showline=False),
    xaxis=dict(gridcolor="rgba(0,0,0,0)", zeroline=False,
               tickfont=dict(color=DS["ink"], size=12), showline=False),
    bargap=0.55,
)
chart_sazonal = pio.to_html(fig2, full_html=False, config=plotly_config)

# Donut uso do solo
nomes_uso = ["Mata", "Pasto verde", "Pasto seco", "Construções", "Água / Sombra"]
vals_uso = [pm, ppv, pps, pc, pa]
# Paleta sincronizada com tiles do Earth Engine (gerar_url_tile_uso_solo)
cores_uso = ["#1b7837", "#92c5de", "#f4a582", "#d6604d", "#2166ac"]
fig3 = go.Figure(go.Pie(
    labels=nomes_uso, values=vals_uso, hole=0.72, sort=False, direction="clockwise",
    marker=dict(colors=cores_uso, line=dict(color=DS["surface"], width=3)),
    textinfo="none",
    hovertemplate="<b>%{label}</b><br>%{value}%<extra></extra>",
))
fig3.update_layout(
    font=dict(family=FONT_SANS, color=DS["ink_2"]),
    paper_bgcolor="rgba(0,0,0,0)", showlegend=False, height=320,
    margin=dict(t=10, b=10, l=10, r=10),
    hoverlabel=dict(bgcolor=DS["ink"], bordercolor=DS["ink"],
                    font=dict(family=FONT_MONO, color="#FFFFFF", size=11)),
    annotations=[dict(
        text=f"<span style='font-family:{FONT_MONO};font-size:26px;color:{DS['ink']};'>{area_m2/10_000:.2f}</span><br>"
             f"<span style='font-size:11px;color:{DS['muted']};letter-spacing:0.1em;'>HECTARES</span>",
        x=0.5, y=0.5, showarrow=False,
    )],
)
chart_uso = pio.to_html(fig3, full_html=False, config=plotly_config)

# ============================================================
# MAPA FOLIUM
# ============================================================
# NOTA: URLs de tiles do Earth Engine (url_rgb/url_ndvi/url_uso) expiram em ~24h.
# O site precisa ser regerado (python gerar_site.py) para renovar os tokens.
print("Mapa...")
mapa = folium.Map(
    location=SITIO_CENTER,
    zoom_start=17,
    tiles=None,
    width="100%",
    height="100%",
    control_scale=True,
    zoom_control=True,
    prefer_canvas=True,
)
# Enquadra o mapa no polígono do sítio ao abrir (evita mapa em branco por bounds estranhos)
bounds = gdf.total_bounds  # [minx, miny, maxx, maxy]
mapa.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]], padding=(20, 20))

folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    name="Satélite", attr="Esri", max_zoom=19, control=False,
).add_to(mapa)

# Camadas do Earth Engine são overlays (ficam sobre o satélite). Isso evita
# o fundo cinza quando só o polígono do sítio é coberto pelo tile.
folium.TileLayer(tiles=url_rgb, name="Sentinel-2", attr="ESA Copernicus",
                 overlay=True, control=True, show=False, max_zoom=19, opacity=0.95).add_to(mapa)
folium.TileLayer(tiles=url_ndvi, name="Vegetação (NDVI)", attr="ESA Copernicus",
                 overlay=True, control=True, show=False, max_zoom=19, opacity=0.85).add_to(mapa)
folium.TileLayer(tiles=url_uso, name="Uso do Solo (IA)", attr="Classificação ML",
                 overlay=True, control=True, show=True, max_zoom=19, opacity=0.80).add_to(mapa)

folium.GeoJson(
    gdf.to_json(),
    name="Limite do sítio",
    style_function=lambda x: {"fillColor": "transparent", "color": "#fbbf24", "weight": 2.5, "fillOpacity": 0, "dashArray": "6,3"},
).add_to(mapa)

folium.LayerControl(collapsed=False, position="topright").add_to(mapa)

# JS auxiliar dentro do iframe do mapa:
#  (1) torna overlays EE mutuamente exclusivos
#  (2) emite postMessage pro parent avisando a camada ativa
from branca.element import Element
mapa.get_root().html.add_child(Element("""
<script>
document.addEventListener('DOMContentLoaded', function() {
    var exclusive = ['Sentinel-2', 'Vegetação (NDVI)', 'Uso do Solo (IA)'];
    function emitActive() {
        var active = null;
        document.querySelectorAll('.leaflet-control-layers-overlays label').forEach(function(lbl) {
            var text = (lbl.textContent || '').trim();
            var input = lbl.querySelector('input[type=checkbox]');
            if (input && input.checked && exclusive.indexOf(text) !== -1) active = text;
        });
        try { window.parent.postMessage({type: 'geositio-layer', layer: active}, '*'); } catch(e) {}
    }
    setTimeout(function() {
        var labels = document.querySelectorAll('.leaflet-control-layers-overlays label');
        labels.forEach(function(lbl) {
            var text = (lbl.textContent || '').trim();
            if (exclusive.indexOf(text) === -1) return;
            var input = lbl.querySelector('input[type=checkbox]');
            if (!input) return;
            input.addEventListener('change', function(ev) {
                if (input.checked) {
                    labels.forEach(function(other) {
                        if (other === lbl) return;
                        var t = (other.textContent || '').trim();
                        if (exclusive.indexOf(t) === -1) return;
                        var i = other.querySelector('input[type=checkbox]');
                        if (i && i.checked) { i.checked = false; i.dispatchEvent(new Event('click')); }
                    });
                }
                setTimeout(emitActive, 30);
            });
        });
        emitActive();
    }, 250);
});
</script>
"""))

mapa_html = mapa._repr_html_()

# ============================================================
# HTML
# ============================================================
print("Montando site...")

def kpi(valor, label, sub="", trend=""):
    trend_html = f'<span class="kpi-trend">{trend}</span>' if trend else ""
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ''
    return f'<div class="kpi"><div class="kpi-label">{label} {trend_html}</div><div class="kpi-val">{valor}</div>{sub_html}</div>'

def inline_metric(valor, label, sub=""):
    sub_html = f'<div class="inline-metric-sub">{sub}</div>' if sub else ''
    return f'<div class="inline-metric"><div class="inline-metric-label">{label}</div><div class="inline-metric-val">{valor}</div>{sub_html}</div>'

def zona_stat(label, valor):
    return f'<div class="zona-stat"><div class="zona-stat-label">{label}</div><div class="zona-stat-val">{valor}</div></div>'

def zona_stats(*pares):
    return '<div class="zona-stats">' + "".join(zona_stat(l, v) for l, v in pares) + '</div>'

def uso_row(cor, nome, pct, desc):
    return f'<div class="uso-row"><div class="uso-dot" style="background:{cor}"></div><div class="uso-name">{nome}</div><div class="uso-pct">{pct}</div><div class="uso-desc">{desc}</div></div>'

def card(titulo, corpo):
    return f'<div class="card"><h4>{titulo}</h4><p>{corpo}</p></div>'

def animal_row(nome, qtd, onde, corpo, tag=""):
    tag_html = f'<div class="animal-tag">{tag}</div>' if tag else '<div></div>'
    return f'<div class="animal-row"><div><div class="animal-name">{nome}</div><div class="animal-onde">{onde}</div></div><div class="animal-qtd">{qtd}</div><div class="animal-desc">{corpo}</div>{tag_html}</div>'

html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sitio Monteiro Lobato</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700&family=Geist+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
/* ============================================================
   GeoSítio — Refined Minimalism Dashboard (v2)
   Inspired by Vercel / Anthropic / Linear
   ============================================================ */
:root {{
    --bg: #FAFAFA;
    --surface: #FFFFFF;
    --surface-2: #F4F4F5;
    --surface-glass: rgba(255, 255, 255, 0.72);
    --border: #E4E4E7;
    --border-subtle: rgba(9, 9, 11, 0.06);
    --border-strong: #D4D4D8;
    --ink: #09090B;
    --ink-2: #27272A;
    --ink-3: #52525B;
    --muted: #71717A;
    --muted-2: #A1A1AA;
    --accent: #65A30D;
    --accent-ink: #3F6212;
    --accent-glow: rgba(101, 163, 13, 0.16);
    --accent-2: #0EA5E9;
    --warn: #EAB308;
    --danger: #DC2626;
    --radius-sm: 6px;
    --radius: 10px;
    --radius-lg: 14px;
    --radius-xl: 20px;
    --shadow-xs: 0 1px 0 rgba(9, 9, 11, 0.04);
    --shadow-sm: 0 1px 2px rgba(9, 9, 11, 0.04), 0 0 0 1px rgba(9, 9, 11, 0.03);
    --shadow-md: 0 4px 16px -4px rgba(9, 9, 11, 0.08), 0 0 0 1px rgba(9, 9, 11, 0.04);
    --shadow-lg: 0 12px 40px -12px rgba(9, 9, 11, 0.18), 0 0 0 1px rgba(9, 9, 11, 0.04);
    --ff-sans: 'Geist', ui-sans-serif, system-ui, sans-serif;
    --ff-mono: 'Geist Mono', ui-monospace, 'SF Mono', Menlo, monospace;
    --ease: cubic-bezier(0.32, 0.72, 0, 1);
    --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
}}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html {{ scroll-behavior: smooth; scroll-padding-top: 80px; }}
body {{
    font-family: var(--ff-sans);
    background: var(--bg);
    color: var(--ink);
    line-height: 1.55;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    text-rendering: optimizeLegibility;
    font-feature-settings: "cv11", "ss01", "ss03";
    font-variant-numeric: tabular-nums;
    overflow-x: hidden;
}}
::selection {{ background: var(--ink); color: #fff; }}
:focus-visible {{ outline: 2px solid var(--ink); outline-offset: 2px; border-radius: 4px; }}

a {{ color: inherit; text-decoration: none; }}
a.link {{
    color: var(--ink);
    border-bottom: 1px solid var(--border-strong);
    transition: border-color .15s var(--ease);
}}
a.link:hover {{ border-bottom-color: var(--ink); }}

h1, h2, h3, h4 {{
    font-family: var(--ff-sans);
    font-weight: 500;
    letter-spacing: -0.022em;
    color: var(--ink);
    line-height: 1.08;
}}

.mono {{ font-family: var(--ff-mono); font-feature-settings: "zero", "ss02"; }}
.num {{ font-variant-numeric: tabular-nums; font-feature-settings: "cv11"; }}

abbr[title] {{ border-bottom: 1px dotted var(--border-strong); cursor: help; text-decoration: none; color: inherit; }}

/* ============================================================
   Grain texture overlay (body)
   ============================================================ */
body::before {{
    content: "";
    position: fixed;
    inset: 0;
    pointer-events: none;
    opacity: 0.4;
    z-index: 1;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.92' numOctaves='2' stitchTiles='stitch'/%3E%3CfeColorMatrix values='0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.04 0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
    mix-blend-mode: multiply;
}}

/* ============================================================
   Sticky navbar
   ============================================================ */
.navbar {{
    position: sticky; top: 0; z-index: 50;
    backdrop-filter: saturate(180%) blur(12px);
    -webkit-backdrop-filter: saturate(180%) blur(12px);
    background: rgba(250, 250, 250, 0.78);
    border-bottom: 1px solid var(--border-subtle);
}}
.navbar-inner {{
    max-width: 1280px; margin: 0 auto;
    padding: 14px 24px;
    display: flex; align-items: center; justify-content: space-between;
    gap: 24px;
}}
.brand {{
    display: inline-flex; align-items: center; gap: 10px;
    font-weight: 600; font-size: 14px; letter-spacing: -0.01em;
    color: var(--ink);
}}
.brand-mark {{
    width: 22px; height: 22px; border-radius: 6px;
    background: var(--ink);
    display: inline-flex; align-items: center; justify-content: center;
    color: var(--accent);
    font-family: var(--ff-mono); font-weight: 600; font-size: 12px;
}}
.nav-meta {{
    font-size: 12px; color: var(--muted);
    display: flex; align-items: center; gap: 16px;
    font-family: var(--ff-mono);
}}
.nav-meta .dot {{ width: 6px; height: 6px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 0 3px var(--accent-glow); }}
@media (max-width: 720px) {{ .nav-meta {{ display: none; }} }}

/* ============================================================
   Hero com mesh gradient
   ============================================================ */
.hero {{
    position: relative;
    padding: 96px 24px 80px;
    overflow: hidden;
    border-bottom: 1px solid var(--border-subtle);
}}
.hero::before {{
    content: ""; position: absolute; inset: -40%;
    background:
        radial-gradient(ellipse 40% 35% at 15% 25%, rgba(101, 163, 13, 0.14), transparent 60%),
        radial-gradient(ellipse 45% 40% at 85% 15%, rgba(14, 165, 233, 0.10), transparent 60%),
        radial-gradient(ellipse 50% 30% at 50% 85%, rgba(9, 9, 11, 0.05), transparent 70%);
    filter: blur(40px);
    z-index: 0;
    pointer-events: none;
}}
.hero-inner {{ max-width: 1080px; margin: 0 auto; position: relative; z-index: 2; }}
.hero-eyebrow {{
    display: inline-flex; align-items: center; gap: 10px;
    padding: 6px 14px 6px 8px;
    background: var(--surface-glass);
    backdrop-filter: blur(8px);
    border: 1px solid var(--border);
    border-radius: 999px;
    font-family: var(--ff-mono);
    font-size: 12px;
    color: var(--ink-2);
    margin-bottom: 28px;
    box-shadow: var(--shadow-xs);
}}
.hero-eyebrow .dot {{ width: 6px; height: 6px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 0 3px var(--accent-glow); }}
.hero h1 {{
    font-size: clamp(2.5rem, 6vw, 4.5rem);
    font-weight: 500;
    letter-spacing: -0.035em;
    line-height: 1.02;
    margin-bottom: 24px;
    max-width: 880px;
}}
.hero h1 em {{
    font-style: normal;
    color: var(--muted);
    font-weight: 400;
}}
.hero .lede {{
    font-size: 1.125rem;
    color: var(--ink-3);
    max-width: 620px;
    line-height: 1.6;
    margin-bottom: 48px;
}}

/* ============================================================
   KPI Cards no hero — glass
   ============================================================ */
.kpi-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 12px;
    max-width: 1080px;
    margin: 0 auto;
    position: relative; z-index: 2;
}}
.kpi {{
    padding: 20px 20px 18px;
    background: var(--surface-glass);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-xs);
    transition: transform .3s var(--ease-out), box-shadow .3s var(--ease-out), border-color .3s var(--ease-out);
    position: relative;
    overflow: hidden;
}}
.kpi::after {{
    content: ""; position: absolute; inset: 0 0 auto 0; height: 1px;
    background: linear-gradient(90deg, transparent, rgba(9, 9, 11, 0.08), transparent);
}}
.kpi:hover {{ transform: translateY(-2px); box-shadow: var(--shadow-md); border-color: var(--border-strong); }}
.kpi-label {{
    font-size: 11px;
    font-family: var(--ff-mono);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
    margin-bottom: 10px;
    display: flex; align-items: center; gap: 6px;
}}
.kpi-val {{
    font-size: 1.875rem;
    font-weight: 500;
    letter-spacing: -0.025em;
    color: var(--ink);
    line-height: 1;
    font-variant-numeric: tabular-nums;
    font-feature-settings: "cv11";
}}
.kpi-sub {{
    font-size: 12px;
    color: var(--muted);
    margin-top: 6px;
    font-family: var(--ff-mono);
}}
.kpi-trend {{
    display: inline-flex; align-items: center; gap: 4px;
    padding: 2px 8px; border-radius: 4px;
    font-size: 11px; font-family: var(--ff-mono); font-weight: 500;
    background: var(--accent-glow);
    color: var(--accent-ink);
}}

/* ============================================================
   Layout com TOC sticky
   ============================================================ */
.layout {{
    max-width: 1280px;
    margin: 0 auto;
    padding: 64px 24px 96px;
    display: grid;
    grid-template-columns: 220px minmax(0, 1fr);
    gap: 64px;
    align-items: start;
}}
@media (max-width: 1024px) {{ .layout {{ grid-template-columns: 1fr; gap: 32px; padding: 48px 20px 72px; }} }}

.toc {{
    position: sticky;
    top: 80px;
    padding-top: 4px;
    font-size: 13px;
}}
@media (max-width: 1024px) {{ .toc {{ display: none; }} }}
.toc-label {{
    font-family: var(--ff-mono);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--muted);
    margin-bottom: 14px;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--border);
}}
.toc ol {{ list-style: none; counter-reset: toc; display: flex; flex-direction: column; gap: 2px; }}
.toc li {{ counter-increment: toc; }}
.toc a {{
    display: flex; align-items: center; gap: 10px;
    padding: 8px 10px 8px 12px;
    border-radius: 6px;
    color: var(--muted);
    transition: all .15s var(--ease);
    position: relative;
    line-height: 1.4;
}}
.toc a::before {{
    content: counter(toc, decimal-leading-zero);
    font-family: var(--ff-mono);
    font-size: 10px;
    color: var(--muted-2);
    letter-spacing: 0.05em;
}}
.toc a:hover {{ color: var(--ink); background: var(--surface-2); }}
.toc a.active {{ color: var(--ink); background: var(--surface); box-shadow: var(--shadow-xs); }}
.toc a.active::after {{
    content: ""; position: absolute; right: 10px;
    width: 5px; height: 5px; border-radius: 50%;
    background: var(--accent);
}}

/* ============================================================
   Seções dashboard
   ============================================================ */
.main-col {{ min-width: 0; display: flex; flex-direction: column; gap: 64px; }}
.section {{
    scroll-margin-top: 80px;
}}
.section-head {{
    display: flex; justify-content: space-between; align-items: flex-end;
    gap: 24px; margin-bottom: 28px;
    padding-bottom: 20px;
    border-bottom: 1px solid var(--border);
}}
.section-head-left {{ flex: 1; min-width: 0; max-width: 760px; }}
.section-tag {{
    font-family: var(--ff-mono);
    font-size: 11px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 12px;
}}
.section h2 {{
    font-size: clamp(1.5rem, 2.8vw, 2rem);
    font-weight: 500;
    letter-spacing: -0.025em;
    color: var(--ink);
    margin-bottom: 12px;
    max-width: 640px;
}}
.section .dek {{
    font-size: 14.5px;
    color: var(--ink-3);
    line-height: 1.6;
    max-width: 620px;
}}
.section h3 {{
    font-family: var(--ff-sans);
    font-size: 1rem;
    font-weight: 600;
    color: var(--ink);
    margin: 32px 0 12px;
    letter-spacing: -0.01em;
}}

/* ============================================================
   Card / panel
   ============================================================ */
.panel {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 24px;
    box-shadow: var(--shadow-xs);
}}
.panel-pad-lg {{ padding: 32px; }}
.panel-head {{
    display: flex; justify-content: space-between; align-items: baseline;
    margin-bottom: 20px;
    gap: 16px;
}}
.panel-title {{
    font-size: 14px; font-weight: 600;
    color: var(--ink);
    font-family: var(--ff-sans);
    letter-spacing: -0.005em;
}}
.panel-meta {{ font-family: var(--ff-mono); font-size: 11px; color: var(--muted); }}

/* ============================================================
   Map
   ============================================================ */
.map-panel {{
    border-radius: var(--radius-lg);
    overflow: hidden;
    border: 1px solid var(--border);
    background: var(--surface-2);
    box-shadow: var(--shadow-xs);
    position: relative;
    height: 560px;
    min-height: 420px;
    z-index: 1;
}}
.map-panel iframe {{
    border: none !important;
    display: block;
    width: 100% !important;
    height: 100% !important;
    min-height: 420px;
    position: absolute;
    inset: 0;
}}
/* Placeholder se o iframe não carregar */
.map-panel::before {{
    content: "Carregando mapa...";
    position: absolute; inset: 0;
    display: flex; align-items: center; justify-content: center;
    color: var(--muted);
    font-size: 13px;
    font-family: var(--ff-mono);
    z-index: 0;
}}
@media (max-width: 640px) {{
    .map-panel {{ height: 420px; }}
}}

.legend {{
    padding: 16px 0 0;
    min-height: 40px;
    position: relative;
}}
.legend-group {{
    display: none;
    flex-direction: column;
    gap: 12px;
    animation: fadeUp .25s var(--ease-out);
}}
.legend-group.active {{ display: flex; }}
.legend-row {{
    display: flex; flex-wrap: wrap; gap: 6px; align-items: center;
}}
.legend-label {{
    font-family: var(--ff-mono);
    font-size: 10.5px;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--muted);
    margin-right: 6px;
    padding-right: 10px;
    border-right: 1px solid var(--border);
    line-height: 1;
    padding-top: 4px; padding-bottom: 4px;
}}
.legend-chip {{
    display: inline-flex; align-items: center; gap: 8px;
    padding: 6px 12px 6px 10px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 999px;
    font-size: 12px; color: var(--ink-2);
    transition: background .15s var(--ease);
}}
.legend-chip .dot {{ width: 8px; height: 8px; border-radius: 2px; flex-shrink: 0; }}
.legend-chip-plain {{
    background: transparent;
    border-color: transparent;
    color: var(--muted);
    font-style: italic;
    padding-left: 2px;
}}
.legend-scale {{
    display: inline-flex; flex-direction: column; gap: 4px;
    margin-left: 6px;
}}
.legend-gradient {{
    display: block;
    width: 200px; height: 10px;
    border-radius: 2px;
    background: linear-gradient(90deg, #d73027 0%, #fee08b 35%, #a6d96a 65%, #1a9850 100%);
    border: 1px solid var(--border);
}}
.legend-scale-labels {{
    display: flex; justify-content: space-between;
    width: 200px;
    font-size: 10px;
    color: var(--muted);
    font-family: var(--ff-mono);
    text-transform: uppercase;
    letter-spacing: 0.06em;
}}
.legend-explain {{
    font-size: 13px;
    color: var(--ink-3);
    line-height: 1.6;
    max-width: 760px;
    padding: 14px 16px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    margin: 0;
}}
.legend-explain strong {{ color: var(--ink); font-weight: 600; }}

/* ============================================================
   Uso do solo — donut + lista
   ============================================================ */
.uso-grid {{
    display: grid;
    grid-template-columns: 340px 1fr;
    gap: 32px;
    align-items: center;
}}
@media (max-width: 820px) {{ .uso-grid {{ grid-template-columns: 1fr; gap: 16px; }} }}

.uso-list {{ display: flex; flex-direction: column; }}
.uso-row {{
    display: grid;
    grid-template-columns: 14px 120px 56px minmax(0, 1fr);
    gap: 16px;
    align-items: center;
    padding: 14px 0;
    border-bottom: 1px solid var(--border-subtle);
}}
.uso-row:last-child {{ border-bottom: none; }}
.uso-dot {{ width: 10px; height: 10px; border-radius: 2px; justify-self: center; }}
.uso-name {{ font-size: 13.5px; font-weight: 500; color: var(--ink); }}
.uso-pct {{ font-family: var(--ff-mono); font-size: 13.5px; color: var(--ink); font-weight: 500; text-align: right; }}
.uso-desc {{ font-size: 12.5px; color: var(--muted); line-height: 1.5; }}
@media (max-width: 560px) {{ .uso-row {{ grid-template-columns: 14px 1fr 56px; gap: 12px; }} .uso-desc {{ display: none; }} }}

/* ============================================================
   Tabs zonas
   ============================================================ */
.tabs {{
    display: flex; gap: 4px;
    padding: 4px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 10px;
    margin-bottom: 24px;
    overflow-x: auto;
    width: fit-content; max-width: 100%;
}}
.tab {{
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 500;
    color: var(--muted);
    cursor: pointer;
    border: none;
    background: transparent;
    border-radius: 7px;
    transition: all .18s var(--ease);
    white-space: nowrap;
    font-family: var(--ff-sans);
    letter-spacing: -0.005em;
}}
.tab:hover {{ color: var(--ink); }}
.tab.active {{ color: var(--ink); background: var(--surface); box-shadow: var(--shadow-xs); }}
.tab-content {{ display: none; }}
.tab-content.active {{ display: block; animation: fadeUp .3s var(--ease-out); }}

@keyframes fadeUp {{
    from {{ opacity: 0; transform: translateY(6px); }}
    to {{ opacity: 1; transform: translateY(0); }}
}}

/* ============================================================
   Zona metadata strip
   ============================================================ */
.zona-stats {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
    gap: 0;
    margin-bottom: 24px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
}}
.zona-stat {{
    padding: 16px 20px;
    border-right: 1px solid var(--border);
}}
.zona-stat:last-child {{ border-right: none; }}
@media (max-width: 560px) {{ .zona-stat {{ border-right: none; border-bottom: 1px solid var(--border); }} .zona-stat:last-child {{ border-bottom: none; }} }}
.zona-stat-label {{
    font-family: var(--ff-mono);
    font-size: 10px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 4px;
}}
.zona-stat-val {{
    font-size: 1.125rem;
    font-weight: 500;
    color: var(--ink);
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.015em;
}}

/* ============================================================
   Tabelas minimalistas
   ============================================================ */
table {{ width: 100%; border-collapse: collapse; font-size: 13.5px; margin: 16px 0; table-layout: fixed; }}
th {{
    color: var(--muted);
    font-weight: 500;
    text-align: left;
    padding: 12px 16px 12px 0;
    font-size: 10.5px;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    border-bottom: 1px solid var(--border);
    font-family: var(--ff-mono);
    vertical-align: bottom;
    white-space: nowrap;
}}
td {{
    padding: 14px 16px 14px 0;
    border-bottom: 1px solid var(--border-subtle);
    color: var(--ink-2);
    vertical-align: top;
    line-height: 1.5;
    word-wrap: break-word;
}}
th:first-child, td:first-child {{ padding-left: 0; }}
td:last-child, th:last-child {{ padding-right: 0; text-align: left; }}
td strong {{ color: var(--ink); font-weight: 500; }}
tr:last-child td {{ border-bottom: none; }}
/* Tabelas 3-col (uso / rec / detalhe): 1ª coluna mais larga */
table th:first-child, table td:first-child {{ width: 26%; }}
/* Tabelas 4-col padronizadas (.t-quad): nome 22% / desc 42% / col3 18% / col4 18% */
table.t-quad th:nth-child(1), table.t-quad td:nth-child(1) {{ width: 22%; }}
table.t-quad th:nth-child(2), table.t-quad td:nth-child(2) {{ width: 42%; }}
table.t-quad th:nth-child(3), table.t-quad td:nth-child(3) {{ width: 18%; white-space: nowrap; }}
table.t-quad th:nth-child(4), table.t-quad td:nth-child(4) {{ width: 18%; white-space: nowrap; }}
@media (max-width: 640px) {{
    table, table.t-quad {{ table-layout: auto; font-size: 13px; }}
    table th, table td, table.t-quad th, table.t-quad td {{ width: auto !important; white-space: normal; }}
}}

/* Sub-panel — quando temos várias tabelas numa mesma seção */
.subpanel {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px 24px 8px;
    margin: 16px 0;
    box-shadow: var(--shadow-xs);
}}
.subpanel-title {{
    font-family: var(--ff-mono);
    font-size: 11px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    padding-bottom: 14px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 4px;
    display: flex; align-items: baseline; justify-content: space-between; gap: 16px;
}}
.subpanel-title .subpanel-meta {{ color: var(--muted-2); font-size: 10.5px; font-weight: 400; letter-spacing: 0.06em; }}
.subpanel table {{ margin: 0; }}
.subpanel table tr:last-child td {{ border-bottom: none; padding-bottom: 12px; }}

/* ============================================================
   Animais — lista editorial com hover
   ============================================================ */
.animal-list {{
    display: flex; flex-direction: column;
    border-top: 1px solid var(--border);
}}
.animal-row {{
    display: grid;
    grid-template-columns: 200px 180px minmax(0, 1fr) 140px;
    gap: 24px;
    padding: 20px 16px;
    border-bottom: 1px solid var(--border);
    align-items: start;
    transition: background .15s var(--ease);
    margin: 0 -16px;
    border-radius: 8px;
}}
.animal-row:hover {{ background: var(--surface); }}
.animal-row > * {{ min-width: 0; }}
@media (max-width: 900px) {{
    .animal-row {{ grid-template-columns: 180px 160px minmax(0, 1fr); gap: 20px; }}
    .animal-row .animal-tag {{ display: none; }}
}}
@media (max-width: 640px) {{
    .animal-row {{ grid-template-columns: 1fr; gap: 6px; padding: 18px 16px; }}
}}
.animal-name {{
    font-size: 15px;
    font-weight: 600;
    color: var(--ink);
    letter-spacing: -0.012em;
    line-height: 1.3;
}}
.animal-qtd {{
    font-family: var(--ff-mono);
    font-size: 13px;
    color: var(--ink);
    font-weight: 500;
    font-feature-settings: "zero";
    line-height: 1.4;
    padding-top: 2px;
}}
.animal-onde {{
    font-size: 10.5px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-top: 6px;
    font-family: var(--ff-mono);
    line-height: 1.3;
}}
.animal-desc {{
    font-size: 13.5px;
    color: var(--ink-3);
    line-height: 1.55;
    padding-top: 1px;
}}
.animal-tag {{
    font-size: 11px;
    font-weight: 500;
    color: var(--accent-ink);
    background: var(--accent-glow);
    padding: 4px 10px;
    border-radius: 6px;
    font-family: var(--ff-mono);
    white-space: nowrap;
    justify-self: end;
    align-self: start;
    line-height: 1.5;
}}

/* ============================================================
   Alerts minimalistas
   ============================================================ */
.alert {{
    padding: 14px 18px;
    font-size: 13.5px;
    margin: 16px 0;
    line-height: 1.55;
    border-radius: var(--radius);
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--ink-2);
    display: flex; gap: 12px; align-items: flex-start;
}}
.alert::before {{
    content: ""; flex-shrink: 0;
    width: 6px; height: 6px; border-radius: 50%;
    margin-top: 7px;
}}
.alert strong {{ color: var(--ink); font-weight: 600; }}
.alert-green::before {{ background: var(--accent); box-shadow: 0 0 0 3px var(--accent-glow); }}
.alert-yellow::before {{ background: var(--warn); box-shadow: 0 0 0 3px rgba(234, 179, 8, 0.16); }}
.alert-blue::before {{ background: var(--accent-2); box-shadow: 0 0 0 3px rgba(14, 165, 233, 0.16); }}
.alert-red::before {{ background: var(--danger); box-shadow: 0 0 0 3px rgba(220, 38, 38, 0.16); }}

/* ============================================================
   Chart wrapper
   ============================================================ */
.chart {{ margin: 8px -12px; }}
.chart-caption {{
    font-size: 12.5px;
    color: var(--muted);
    margin-top: 14px;
    line-height: 1.55;
    padding-top: 14px;
    border-top: 1px dashed var(--border);
}}

/* ============================================================
   Cards genéricos (mata)
   ============================================================ */
.cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; margin: 16px 0; }}
.card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px;
    transition: transform .2s var(--ease), box-shadow .2s var(--ease);
}}
.card:hover {{ transform: translateY(-2px); box-shadow: var(--shadow-md); }}
.card h4 {{ font-size: 14px; font-weight: 600; color: var(--ink); margin-bottom: 8px; letter-spacing: -0.01em; }}
.card p {{ font-size: 13px; color: var(--ink-3); line-height: 1.6; }}

/* ============================================================
   Highlight metrics inline (saúde vegetação)
   ============================================================ */
.inline-metrics {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 0;
    margin-top: 24px;
    border-top: 1px solid var(--border);
    border-bottom: 1px solid var(--border);
}}
.inline-metric {{
    padding: 18px 0 18px 20px;
    border-right: 1px solid var(--border);
}}
.inline-metric:last-child {{ border-right: none; }}
@media (max-width: 560px) {{ .inline-metric {{ border-right: none; border-bottom: 1px solid var(--border); }} .inline-metric:last-child {{ border-bottom: none; }} }}
.inline-metric-label {{
    font-family: var(--ff-mono);
    font-size: 10px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 6px;
}}
.inline-metric-val {{
    font-size: 1.375rem;
    font-weight: 500;
    color: var(--ink);
    letter-spacing: -0.02em;
    font-variant-numeric: tabular-nums;
}}
.inline-metric-sub {{ font-size: 12px; color: var(--muted); margin-top: 3px; font-family: var(--ff-mono); }}

/* ============================================================
   Details / metodologia
   ============================================================ */
details {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-xs);
    overflow: hidden;
    transition: box-shadow .2s var(--ease);
}}
details[open] {{ box-shadow: var(--shadow-sm); }}
details summary {{
    padding: 20px 24px;
    cursor: pointer;
    font-weight: 500;
    color: var(--ink);
    font-family: var(--ff-sans);
    list-style: none;
    display: flex; align-items: center; justify-content: space-between;
    font-size: 14px;
    letter-spacing: -0.005em;
}}
details summary::-webkit-details-marker {{ display: none; }}
details summary::after {{
    content: "+"; font-family: var(--ff-mono); color: var(--muted); font-size: 18px; font-weight: 300;
    transition: transform .2s var(--ease);
}}
details[open] summary::after {{ content: "−"; }}
details > div {{ padding: 0 24px 24px; }}
.grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 32px; align-items: start; }}
@media (max-width: 720px) {{ .grid-2 {{ grid-template-columns: 1fr; gap: 20px; }} }}

/* ============================================================
   Footer
   ============================================================ */
footer {{
    max-width: 1280px; margin: 0 auto;
    padding: 48px 24px 64px;
    display: flex; justify-content: space-between; align-items: flex-end;
    gap: 24px;
    border-top: 1px solid var(--border);
    flex-wrap: wrap;
    color: var(--muted);
    font-size: 12.5px;
    font-family: var(--ff-mono);
}}
footer strong {{ color: var(--ink); font-family: var(--ff-sans); font-weight: 600; font-size: 14px; }}
.footer-meta {{ color: var(--muted); font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.08em; }}

/* ============================================================
   Reveal on scroll
   ============================================================ */
.reveal {{ opacity: 0; transform: translateY(12px); transition: opacity .6s var(--ease-out), transform .6s var(--ease-out); }}
.reveal.visible {{ opacity: 1; transform: translateY(0); }}

@media (prefers-reduced-motion: reduce) {{
    *, *::before, *::after {{ animation: none !important; transition: none !important; }}
    .reveal {{ opacity: 1; transform: none; }}
}}
</style>
</head>
<body>

<nav class="navbar">
    <div class="navbar-inner">
        <a class="brand" href="#top">
            <span class="brand-mark">G</span>
            <span>GeoSítio</span>
        </a>
        <div class="nav-meta">
            <span><span class="dot"></span> Monteiro Lobato · SP</span>
            <span>v1.0 · {pd.Timestamp.today().strftime('%b %Y')}</span>
        </div>
    </div>
</nav>

<header class="hero" id="top">
    <div class="hero-inner">
        <div class="hero-eyebrow">
            <span class="dot"></span>
            Relatório geoespacial — 3 anos de análise
        </div>
        <h1>Um retrato do sítio em Monteiro Lobato,<br><em>visto do espaço.</em></h1>
        <p class="lede">Análise de {area_m2/10_000:.2f} hectares na Serra da Mantiqueira usando {qtd} imagens do Sentinel-2 e {len(df)} observações de três anos. O que tem no sítio, como a vegetação se comporta e o que faz sentido plantar ou criar em cada zona — embasado em dados.</p>
    </div>

    <div class="kpi-grid" style="margin-top: 24px;">
        {kpi(f"{area_m2/10_000:.2f} <span class='mono' style='font-size:0.55em;color:var(--muted);font-weight:400;'>ha</span>", "Área total", f"{area_m2:,.0f} m²")}
        {kpi(f"{sn['media']:.2f}", "NDVI médio", f"Vegetação: {estado.lower()}")}
        {kpi(f"{var:+.1f}<span class='mono' style='font-size:0.55em;color:var(--muted);font-weight:400;'>%</span>", "Tendência", "3 anos", "↑" if var >= 0 else "↓")}
        {kpi(f"{se['minimo']:.0f}–{se['maximo']:.0f} <span class='mono' style='font-size:0.55em;color:var(--muted);font-weight:400;'>m</span>", "Altitude", f"Desnível {se['desnivel']:.0f} m")}
        {kpi(f"{sd['media']:.1f}°", "Declividade", "Inclinação média")}
    </div>
</header>

<div class="layout">

    <!-- TOC -->
    <aside class="toc" aria-label="Índice do relatório">
        <div class="toc-label">Neste relatório</div>
        <ol>
            <li><a href="#mapa">Mapa do sítio</a></li>
            <li><a href="#uso">Uso do solo</a></li>
            <li><a href="#zonas">Recomendações por zona</a></li>
            <li><a href="#vegetacao">Saúde da vegetação</a></li>
            <li><a href="#ciclo">Ciclo anual</a></li>
            <li><a href="#animais">Criação animal</a></li>
            <li><a href="#metodologia">Metodologia</a></li>
        </ol>
    </aside>

    <main class="main-col">

        <!-- MAPA -->
        <section class="section reveal" id="mapa">
            <div class="section-head">
                <div class="section-head-left">
                    <div class="section-tag">01 / Mapa</div>
                    <h2>A propriedade vista de cima</h2>
                    <p class="dek">Imagem real de satélite com classificação automática do terreno. Alterne entre <abbr title="Imagem real da superfície vista de cima.">Satélite</abbr>, <abbr title="Satélite europeu Sentinel-2 da ESA — captura imagens a cada 5 dias com resolução de 10 m.">Sentinel-2</abbr>, <abbr title="Índice de Vegetação por Diferença Normalizada. Mede a saúde da vegetação: 0 é solo nu, 1 é floresta densa.">Vegetação (NDVI)</abbr> e Uso do Solo no canto superior direito do mapa.</p>
                </div>
                <div class="panel-meta">Resolução · 10 m/pixel</div>
            </div>
            <div class="map-panel">{mapa_html}</div>
            <div class="legend" aria-label="Legenda do mapa" id="map-legend">
                <div class="legend-group active" data-layer="uso">
                    <div class="legend-row">
                        <span class="legend-label">Uso do solo</span>
                        <span class="legend-chip"><span class="dot" style="background:#1b7837"></span> Mata</span>
                        <span class="legend-chip"><span class="dot" style="background:#92c5de"></span> Pasto verde</span>
                        <span class="legend-chip"><span class="dot" style="background:#f4a582"></span> Pasto seco</span>
                        <span class="legend-chip"><span class="dot" style="background:#d6604d"></span> Construções</span>
                        <span class="legend-chip"><span class="dot" style="background:#2166ac"></span> Água / Sombra</span>
                    </div>
                    <p class="legend-explain">Um modelo de inteligência artificial analisou a imagem do satélite e separou o terreno em <strong>5 classes de uso do solo</strong>. Cada classe tem cor fixa no mapa e ajuda a decidir onde plantar, preservar ou construir.</p>
                </div>
                <div class="legend-group" data-layer="ndvi">
                    <div class="legend-row">
                        <span class="legend-label">NDVI</span>
                        <span class="legend-scale" aria-hidden="true">
                            <span class="legend-gradient"></span>
                            <span class="legend-scale-labels"><span>solo nu</span><span>vegetação densa</span></span>
                        </span>
                    </div>
                    <p class="legend-explain"><strong>NDVI (Índice de Vegetação por Diferença Normalizada)</strong> mede a saúde da vegetação usando as bandas vermelho e infravermelho do satélite. Escala de 0 a 1: <strong>0</strong> = solo exposto ou seco, <strong>1</strong> = floresta densa e saudável. Áreas vermelhas/amarelas no mapa precisam de atenção; áreas verdes estão saudáveis.</p>
                </div>
                <div class="legend-group" data-layer="sentinel">
                    <div class="legend-row">
                        <span class="legend-label">Sentinel-2</span>
                        <span class="legend-chip legend-chip-plain">Imagem colorida real (R · G · B)</span>
                    </div>
                    <p class="legend-explain"><strong>Sentinel-2</strong> é um satélite europeu da ESA que fotografa a Terra a cada 5 dias com resolução de 10 metros por pixel. Esta camada mostra a imagem real do sítio em cores naturais — o que você veria de um avião. É a base das análises de NDVI e Uso do Solo.</p>
                </div>
                <div class="legend-group" data-layer="none">
                    <div class="legend-row">
                        <span class="legend-label">Satélite</span>
                    </div>
                    <p class="legend-explain">Imagem base do Esri World Imagery. Ative uma das camadas acima para ver a análise do sítio.</p>
                </div>
            </div>
        </section>

        <!-- USO DO SOLO -->
        <section class="section reveal" id="uso">
            <div class="section-head">
                <div class="section-head-left">
                    <div class="section-tag">02 / Composição</div>
                    <h2>O que tem no sítio</h2>
                    <p class="dek">Um modelo de <abbr title="Algoritmo de aprendizado de máquina treinado para identificar padrões de vegetação, solo e água nas imagens.">classificação por IA</abbr> separou o terreno em cinco classes. Cada uma tem papel e vocação distintos.</p>
                </div>
            </div>
            <div class="panel panel-pad-lg">
                <div class="uso-grid">
                    <div class="chart">{chart_uso}</div>
                    <div class="uso-list">
                        {uso_row("#1b7837", "Mata", f"{pm:.0f}%", "Preservar — Código Florestal.")}
                        {uso_row("#92c5de", "Pasto verde", f"{ppv:.0f}%", "Solo mais fértil do sítio.")}
                        {uso_row("#f4a582", "Pasto seco", f"{pps:.0f}%", "Maior área — pastagem.")}
                        {uso_row("#d6604d", "Construções", f"{pc:.0f}%", "Casas, galpões, solo exposto.")}
                        {uso_row("#2166ac", "Água / Sombra", f"{pa:.0f}%", "Zona baixa — local pro tanque.")}
                    </div>
                </div>
            </div>
        </section>

        <!-- ZONAS -->
        <section class="section reveal" id="zonas">
            <div class="section-head">
                <div class="section-head-left">
                    <div class="section-tag">03 / Recomendações</div>
                    <h2>O que plantar e onde</h2>
                    <p class="dek">Cruzamos vegetação (NDVI), inclinação e umidade com as necessidades de cada cultura. Cada zona tem restrições — e oportunidades.</p>
                </div>
            </div>

            <div class="tabs" role="tablist">
                <button class="tab active" onclick="showTab(0)">Pasto verde</button>
                <button class="tab" onclick="showTab(1)">Pasto seco</button>
                <button class="tab" onclick="showTab(2)">Zona baixa</button>
                <button class="tab" onclick="showTab(3)">Mata</button>
                <button class="tab" onclick="showTab(4)">Construções</button>
            </div>

            <div class="tab-content active" id="tab-0">
                {zona_stats(("Área", "0,67 ha"), ("Inclinação", "16,9°"), ("Altitude", "678 m"), ("NDVI", "0,70"))}
                <div class="alert alert-green"><div><strong>Melhor área pra cultivo.</strong> Terreno mais fértil do sítio — vegetação densa indica solo saudável.</div></div>
                <h3>O que plantar aqui</h3>
                <div class="subpanel">
                    <div class="subpanel-title"><span>Frutas recomendadas</span><span class="subpanel-meta">5 opções</span></div>
                <table class="t-quad">
                    <thead><tr><th>Fruta</th><th>Por que funciona</th><th>Plantar</th><th>Colher</th></tr></thead>
                    <tbody>
                    <tr><td><strong>Morango</strong></td><td>Clima ameno ideal; já cultivado na Mantiqueira</td><td>Mar–Abr</td><td>Jun–Nov</td></tr>
                    <tr><td><strong>Amora</strong></td><td>Ótima adaptação a 600–800 m de altitude</td><td>Jun–Ago</td><td>2º ano em diante</td></tr>
                    <tr><td><strong>Framboesa</strong></td><td>Alto valor; mercado gourmet em SJC (40 km)</td><td>Jun–Ago</td><td>2º ano em diante</td></tr>
                    <tr><td><strong>Caqui</strong></td><td>Pouca manutenção; produz muito bem</td><td>Jun–Ago</td><td>Jan–Jun</td></tr>
                    <tr><td><strong>Figo</strong></td><td>Rústico; boa produção sem muitos cuidados</td><td>Jun–Ago</td><td>Jan–Mar</td></tr>
                    </tbody>
                </table>
                </table>
                </div>
                <div class="subpanel">
                    <div class="subpanel-title"><span>Horta</span><span class="subpanel-meta">5 culturas</span></div>
                <table class="t-quad">
                    <thead><tr><th>Cultura</th><th>Época</th><th>Ciclo</th><th>Observação</th></tr></thead>
                    <tbody>
                    <tr><td><strong>Alface / Couve</strong></td><td>Ano todo</td><td>45–60 dias</td><td>Favorecida pelo clima ameno</td></tr>
                    <tr><td><strong>Brócolis / Couve-flor</strong></td><td>Mar–Jul (frio)</td><td>80–120 dias</td><td>Menos pragas na altitude</td></tr>
                    <tr><td><strong>Cenoura / Beterraba</strong></td><td>Mar–Jul</td><td>60–110 dias</td><td>Muito boa em altitude</td></tr>
                    <tr><td><strong>Tomate / Abobrinha</strong></td><td>Set–Fev (chuvas)</td><td>90–120 dias</td><td>Boa renda na venda direta</td></tr>
                    <tr><td><strong>Ervas aromáticas</strong></td><td>Ano todo</td><td>Contínuo</td><td>Alecrim e manjericão</td></tr>
                    </tbody>
                </table>
                </div>
                <div class="alert alert-yellow"><div>Inclinação de 16,9° dificulta mecanização. Plantio em curvas de nível ou terraços é recomendado.</div></div>
            </div>

            <div class="tab-content" id="tab-1">
                {zona_stats(("Área", "1,13 ha"), ("Inclinação", "19,6°"), ("Altitude", "684 m"), ("NDVI", "0,62"))}
                <div class="alert alert-yellow"><div><strong>Maior área do sítio.</strong> Inclinação alta — melhor manter como pastagem do que forçar cultivo mecanizado.</div></div>
                <table>
                    <thead><tr><th>Uso</th><th>Recomendação</th><th>Detalhe</th></tr></thead>
                    <tbody>
                    <tr><td><strong>Gado leiteiro</strong></td><td>2–3 vacas Jersey</td><td>Produção 30–50 L/dia. Queijo, doce de leite.</td></tr>
                    <tr><td><strong>Cabras</strong></td><td>10–15 cabras Saanen</td><td>Queijo gourmet. 8 cabras equivalem a 1 vaca.</td></tr>
                    <tr><td><strong>Mandioca</strong></td><td>Aguenta inclinação</td><td>Set–Nov, colheita 12–18 meses.</td></tr>
                    <tr><td><strong>Milho / feijão</strong></td><td>Alimento + ração</td><td>Set–Nov, colheita 80–120 dias.</td></tr>
                    <tr><td><strong>Banana</strong></td><td>Em áreas protegidas</td><td>Precisa proteção contra vento frio.</td></tr>
                    </tbody>
                </table>
                <div class="alert alert-red"><div><strong>Risco de erosão</strong> em encostas de 19,6°. Evitar solo exposto. Pastagem rotacionada ajuda a estabilizar.</div></div>
            </div>

            <div class="tab-content" id="tab-2">
                {zona_stats(("Área", "0,21 ha"), ("Inclinação", "8°"), ("Altitude", "660 m"), ("Água", "—"))}
                <div class="alert alert-blue"><div><strong>Ponto mais baixo e plano do sítio.</strong> Melhor local pra tanque de peixes ou áreas úmidas.</div></div>
                <h3>Peixes recomendados</h3>
                <table>
                    <thead><tr><th>Peixe</th><th>Funciona</th><th>Por quê</th></tr></thead>
                    <tbody>
                    <tr><td><strong>Carpa</strong></td><td><span style="color:var(--accent-ink);font-weight:500">Sim</span></td><td>Resiste ao frio do inverno. Melhor opção geral.</td></tr>
                    <tr><td><strong>Tilápia</strong></td><td><span style="color:#A16207;font-weight:500">Só verão</span></td><td>Set–abr. Morre abaixo de 10 °C.</td></tr>
                    <tr><td><strong>Lambari</strong></td><td><span style="color:var(--accent-ink);font-weight:500">Sim</span></td><td>Cresce rápido (3 meses). Resistente.</td></tr>
                    <tr><td><strong>Truta</strong></td><td><span style="color:var(--danger);font-weight:500">Não</span></td><td>Precisa altitude acima de 1.000 m.</td></tr>
                    </tbody>
                </table>
                <p style="font-size:13.5px;color:var(--ink-3);margin:16px 0;">Tanque escavado de 300–500 m², profundidade 1,2–1,5 m.</p>
                <h3>Fonte de água</h3>
                <div class="alert alert-blue"><div>O satélite <strong>não detectou água</strong> na superfície dentro do sítio (0 de 357 pontos com índice positivo). O <strong>Ribeirão Sousas</strong> passa perto e pode servir de fonte. Nascentes subterrâneas não aparecem no satélite — verificar no local (solo encharcado, samambaias, musgos).</div></div>
                <h3>Culturas que gostam de umidade</h3>
                <p style="font-size:13.5px;color:var(--ink-3);">Inhame, taioba, agrião, hortelã — combinam com a umidade natural desta zona.</p>
            </div>

            <div class="tab-content" id="tab-3">
                {zona_stats(("Área", "0,71 ha"), ("% do sítio", "21%"), ("Inclinação", "13,6°"), ("NDVI", "0,71"))}
                <div class="alert alert-green"><div><strong>Preservação obrigatória.</strong> Código Florestal exige 20% — o sítio tem 21%, no limite. Qualquer corte reduz a reserva legal.</div></div>
                <div class="cards">
                    {card("Proteção de nascentes", "A mata evita erosão e protege possíveis nascentes no entorno.")}
                    {card("Apicultura na borda", "10–15 caixas. Mel da Mantiqueira tem ótimo mercado: 15–30 kg/caixa/ano. Bônus: polinizam pomar e horta.")}
                </div>
            </div>

            <div class="tab-content" id="tab-4">
                {zona_stats(("Área", "0,88 ha"), ("Inclinação", "15,8°"), ("Altitude", "683 m"))}
                <table>
                    <thead><tr><th>Atividade</th><th>Detalhe</th><th>Renda estimada</th></tr></thead>
                    <tbody>
                    <tr><td><strong>Galinhas caipiras</strong></td><td>50–100 aves · ovo R$ 14–20/dúzia</td><td><span style="color:var(--accent-ink);font-weight:500">R$ 420–600/mês</span></td></tr>
                    <tr><td><strong>Porcos caipiras</strong></td><td>5–10 porcos · linguiça artesanal</td><td>Consumo + venda</td></tr>
                    <tr><td><strong>Turismo rural</strong></td><td>Café colonial, colha-e-pague, pesque-pague</td><td>Variável</td></tr>
                    </tbody>
                </table>
                <div class="alert alert-green"><div>Monteiro Lobato já é destino turístico. São José dos Campos (700 mil hab.) fica a 40 km.</div></div>
            </div>
        </section>

        <!-- VEGETAÇÃO -->
        <section class="section reveal" id="vegetacao">
            <div class="section-head">
                <div class="section-head-left">
                    <div class="section-tag">04 / Vegetação</div>
                    <h2>A vegetação está melhorando ou piorando?</h2>
                    <p class="dek">Acompanhamos o sítio nos últimos três anos com <strong>{len(df)} imagens</strong> do Sentinel-2. A faixa verde marca a zona saudável de NDVI (≥ 0,60). Pontos acima são bons sinais — abaixo, alerta.</p>
                </div>
            </div>
            <div class="panel panel-pad-lg">
                <div class="panel-head">
                    <div class="panel-title">NDVI ao longo de 3 anos</div>
                    <div class="panel-meta">Uma medição por passagem do satélite</div>
                </div>
                <div class="chart">{chart_serie}</div>
                <div class="chart-caption">Cada ponto é uma medição real do Sentinel-2. A linha contínua é a tendência (média móvel de 5 medições). A faixa verde marca NDVI saudável (≥ 0,60).</div>
            </div>
            <div class="inline-metrics">
                {inline_metric(estado, "Veredicto", f"{var:+.1f}% em 3 anos")}
                {inline_metric(mv, "Mês mais verde", "Época das chuvas")}
                {inline_metric(ms, "Mês mais seco", "Inverno da Mantiqueira")}
                {inline_metric(str(len(df)), "Medições", "Sentinel-2 · 3 anos")}
            </div>
        </section>

        <!-- CICLO ANUAL -->
        <section class="section reveal" id="ciclo">
            <div class="section-head">
                <div class="section-head-left">
                    <div class="section-tag">05 / Ciclo</div>
                    <h2>Qual a melhor época do ano?</h2>
                    <p class="dek">A vegetação segue o ciclo de chuvas. Saber isso ajuda a planejar plantio, manejo de pasto e colheita.</p>
                </div>
            </div>
            <div class="panel panel-pad-lg">
                <div class="panel-head">
                    <div class="panel-title">NDVI médio por mês</div>
                    <div class="panel-meta">Todos os anos agregados</div>
                </div>
                <div class="chart">{chart_sazonal}</div>
                <div class="chart-caption">Barras verdes indicam meses saudáveis (NDVI ≥ 0,60), amarelas meses intermediários. As barras verticais em cada coluna mostram a variação entre anos.</div>
            </div>
        </section>

        <!-- ANIMAIS -->
        <section class="section reveal" id="animais">
            <div class="section-head">
                <div class="section-head-left">
                    <div class="section-tag">06 / Criação</div>
                    <h2>Quais animais criar</h2>
                    <p class="dek">Recomendações para {area_m2/10_000:.1f} ha na Serra da Mantiqueira, altitude {se['media']:.0f} m. Priorizamos raças adaptadas ao clima frio de inverno e ao relevo inclinado.</p>
                </div>
            </div>
            <div class="animal-list">
                {animal_row("Gado leiteiro", "2–3 vacas Jersey", "Zona de pasto · 1,8 ha", "Raça menor, come menos. Leite com alto teor de gordura. Produção 30–50 L/dia. Queijo artesanal e doce de leite.")}
                {animal_row("Cabras leiteiras", "10–15 cabras Saanen", "Pasto compartilhado", "8 cabras consomem o mesmo que uma vaca. Queijo gourmet com mercado em São José dos Campos e Campos do Jordão.", "Excelente margem")}
                {animal_row("Galinhas caipiras", "50–100 galinhas", "Próximo às construções", "Cerca de 30 dúzias de ovos por mês. Ovo caipira vale R$ 14–20/dúzia. Investimento baixo, retorno rápido.", "R$ 420–600/mês")}
                {animal_row("Peixes", "Carpa + Tilápia + Lambari", "Tanque na zona baixa", "Carpa resiste ao frio. Tilápia só no verão (set–abr). Tanque escavado 300–500 m². Truta não funciona a 680 m.")}
                {animal_row("Abelhas", "10–15 caixas", "Borda da mata", "Mel da Mantiqueira tem ótimo mercado: 15–30 kg/caixa/ano. Bônus: polinizam pomar e horta.")}
            </div>
        </section>

        <!-- METODOLOGIA -->
        <section class="section reveal" id="metodologia">
            <div class="section-head">
                <div class="section-head-left">
                    <div class="section-tag">07 / Metodologia</div>
                    <h2>Como o relatório foi feito</h2>
                    <p class="dek">Dados brutos, resoluções e fontes. Para quem quiser replicar ou aprofundar.</p>
                </div>
            </div>
            <details>
                <summary>Parâmetros técnicos e estatísticas brutas</summary>
                <div>
                    <div class="grid-2">
                        <div>
                            <h3>Vegetação</h3>
                            <table>
                            <tr><td>NDVI médio</td><td><strong>{sn['media']:.3f}</strong></td></tr>
                            <tr><td>NDVI mín / máx</td><td>{sn['minimo']:.3f} / {sn['maximo']:.3f}</td></tr>
                            <tr><td>Desvio padrão</td><td>{sn['desvio_padrao']:.3f}</td></tr>
                            <tr><td>Imagens analisadas</td><td>{qtd} (último ano)</td></tr>
                            <tr><td>Série temporal</td><td>{len(df)} observações (3 anos)</td></tr>
                            </table>
                        </div>
                        <div>
                            <h3>Terreno</h3>
                            <table>
                            <tr><td>Elevação</td><td>{se['minimo']:.0f} m – {se['maximo']:.0f} m</td></tr>
                            <tr><td>Desnível</td><td>{se['desnivel']:.0f} m</td></tr>
                            <tr><td>Declividade média</td><td>{sd['media']:.1f}° (máx. {sd['maximo']:.1f}°)</td></tr>
                            <tr><td>Resolução satélite</td><td>10 m (Sentinel-2)</td></tr>
                            <tr><td>Resolução terreno</td><td>30 m (SRTM)</td></tr>
                            </table>
                        </div>
                    </div>
                    <p style="color:var(--muted);font-size:12px;margin-top:20px;font-family:var(--ff-mono);">Fontes · ESA Copernicus Sentinel-2 · NASA SRTM · Google Earth Engine · EMBRAPA · IBGE</p>
                </div>
            </details>
        </section>

    </main>
</div>

<footer>
    <div>
        <strong>GeoSítio</strong><br>
        <span class="footer-meta">Inteligência geoespacial · Monteiro Lobato, SP</span>
    </div>
    <div class="footer-meta">
        Build {pd.Timestamp.today().strftime('%Y.%m.%d')} · Sentinel-2 · Earth Engine · Plotly.js · Leaflet
    </div>
</footer>

<script>
function showTab(n) {{
    document.querySelectorAll('.tab-content').forEach((el,i) => el.classList.toggle('active', i===n));
    document.querySelectorAll('.tab').forEach((el,i) => el.classList.toggle('active', i===n));
}}

// Reveal on scroll
const io = new IntersectionObserver((entries) => {{
    entries.forEach(e => {{ if (e.isIntersecting) {{ e.target.classList.add('visible'); io.unobserve(e.target); }} }});
}}, {{ threshold: 0.08, rootMargin: '0px 0px -40px 0px' }});
document.querySelectorAll('.reveal').forEach(el => io.observe(el));

// Legenda dinâmica do mapa — escuta postMessage do iframe do Folium
window.addEventListener('message', function(e) {{
    if (!e.data || e.data.type !== 'geositio-layer') return;
    var layer = e.data.layer;
    var key = 'none';
    if (layer === 'Uso do Solo (IA)') key = 'uso';
    else if (layer === 'Vegetação (NDVI)') key = 'ndvi';
    else if (layer === 'Sentinel-2') key = 'sentinel';
    document.querySelectorAll('#map-legend .legend-group').forEach(function(g) {{
        g.classList.toggle('active', g.dataset.layer === key);
    }});
}});

// Scroll-spy TOC
const sections = document.querySelectorAll('.section[id]');
const tocLinks = document.querySelectorAll('.toc a');
const spy = new IntersectionObserver((entries) => {{
    entries.forEach(e => {{
        if (e.isIntersecting) {{
            const id = e.target.id;
            tocLinks.forEach(a => a.classList.toggle('active', a.getAttribute('href') === '#' + id));
        }}
    }});
}}, {{ rootMargin: '-40% 0px -55% 0px' }});
sections.forEach(s => spy.observe(s));
</script>

</body>
</html>"""

Path("data/sitio.html").write_text(html, encoding="utf-8")
print("\nSite salvo em data/sitio.html")
