"""Utilitários geoespaciais para o projeto GeoSítio."""

from pathlib import Path

import folium
import geopandas as gpd

from src.config import (
    CRS_ANALYSIS,
    CRS_DISPLAY,
    SITIO_CENTER,
    SITIO_KML,
)


def carregar_sitio(kml_path: Path = SITIO_KML) -> gpd.GeoDataFrame:
    """Carrega o polígono do sítio a partir do arquivo KML."""
    gdf = gpd.read_file(kml_path, driver="KML")
    gdf = gdf.set_crs(CRS_DISPLAY)
    return gdf


def criar_mapa_base(
    centro: tuple = SITIO_CENTER,
    zoom: int = 16,
    tiles: str = "OpenStreetMap",
) -> folium.Map:
    """Cria um mapa base do Folium centrado no sítio."""
    mapa = folium.Map(location=centro, zoom_start=zoom, tiles=tiles)

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        name="Satélite",
        attr="Esri",
    ).add_to(mapa)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
        name="Topográfico",
        attr="Esri",
    ).add_to(mapa)
    folium.LayerControl().add_to(mapa)

    return mapa


def adicionar_poligono_sitio(
    mapa: folium.Map,
    gdf: gpd.GeoDataFrame = None,
) -> folium.Map:
    """Adiciona o polígono real do sítio ao mapa."""
    if gdf is None:
        gdf = carregar_sitio()

    folium.GeoJson(
        gdf,
        name="Sítio Monteiro Lobato",
        style_function=lambda x: {
            "fillColor": "#228B22",
            "color": "#FFD700",
            "weight": 3,
            "fillOpacity": 0.2,
        },
        tooltip="Sítio Monteiro Lobato — Área: 32.895 m² (~3,3 ha)",
    ).add_to(mapa)
    return mapa


def reprojetar(gdf: gpd.GeoDataFrame, crs_destino: str = CRS_ANALYSIS) -> gpd.GeoDataFrame:
    """Reprojeta um GeoDataFrame para o CRS de análise."""
    return gdf.to_crs(crs_destino)
