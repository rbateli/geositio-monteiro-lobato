"""Gera o mapa do sítio como HTML standalone."""
import sys
sys.path.append(".")

from src.geo_utils import carregar_sitio, reprojetar
from src.config import SITIO_CENTER

import folium

# Carregar polígono
gdf_sitio = carregar_sitio()
gdf_utm = reprojetar(gdf_sitio)
area_m2 = gdf_utm.area.values[0]
perimetro_m = gdf_utm.length.values[0]

# Criar mapa simples (sem dependências extras que podem ser bloqueadas)
mapa = folium.Map(
    location=SITIO_CENTER,
    zoom_start=17,
    tiles="OpenStreetMap",
)

# Camada de satélite
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    name="Satélite",
    attr="Esri",
).add_to(mapa)

# Camada topográfica (relevo + curvas de nível)
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
    name="Topográfico (Relevo)",
    attr="Esri",
).add_to(mapa)

# Camada de relevo sombreado
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Shaded_Relief/MapServer/tile/{z}/{y}/{x}",
    name="Relevo Sombreado",
    attr="Esri",
).add_to(mapa)

# Hidrografia e estradas (OpenTopoMap)
folium.TileLayer(
    tiles="https://tile.opentopomap.org/{z}/{x}/{y}.png",
    name="OpenTopoMap (Hidrografia)",
    attr='OpenTopoMap',
    max_zoom=17,
).add_to(mapa)

# Cobertura vegetal (Google Terrain)
folium.TileLayer(
    tiles="https://mt1.google.com/vt/lyrs=p&x={x}&y={y}&z={z}",
    name="Terreno (Vegetação)",
    attr="Google",
).add_to(mapa)

# Polígono do sítio
folium.GeoJson(
    gdf_sitio.to_json(),
    name="Sítio Monteiro Lobato",
    style_function=lambda x: {
        "fillColor": "#228B22",
        "color": "#FFD700",
        "weight": 3,
        "fillOpacity": 0.2,
    },
    tooltip=f"Sítio Monteiro Lobato — {area_m2:,.0f} m² (~{area_m2/10_000:.2f} ha)",
).add_to(mapa)

# Marcador simples (sem ícone Font Awesome pra evitar bloqueio de CDN)
folium.CircleMarker(
    location=SITIO_CENTER,
    radius=8,
    color="#FFD700",
    fill=True,
    fill_color="#228B22",
    fill_opacity=0.8,
    popup=f"<b>Sítio Monteiro Lobato</b><br>Área: {area_m2:,.0f} m² ({area_m2/10_000:.2f} ha)<br>Perímetro: {perimetro_m:,.0f} m",
).add_to(mapa)

folium.LayerControl().add_to(mapa)

# Salvar
mapa.save("data/mapa_sitio.html")
print(f"Mapa salvo! Área: {area_m2:,.0f} m² | Perímetro: {perimetro_m:,.0f} m")
