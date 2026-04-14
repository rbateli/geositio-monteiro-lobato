"""Configurações centrais do projeto GeoSítio."""

from pathlib import Path

# Diretórios
ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"
DATA_RAW = DATA_DIR / "raw"
DATA_PROCESSED = DATA_DIR / "processed"
DATA_SAMPLES = DATA_DIR / "samples"

# Coordenadas do sítio em Monteiro Lobato, SP
SITIO_CENTER = (-22.9143532, -45.8387299)
SITIO_KML = DATA_DIR / "Sítio Monteiro Lobato.kml"

# Propriedades do sítio (medidas do Google Earth)
SITIO_AREA_M2 = 32_895.69
SITIO_PERIMETRO_M = 896.95
SITIO_ELEVACAO = {"min": 658.99, "mediana": 684.91, "max": 708.78}

# Sistemas de Referência de Coordenadas
CRS_DISPLAY = "EPSG:4326"        # WGS84 — para visualização em mapas web
CRS_ANALYSIS = "EPSG:31983"      # SIRGAS 2000 / UTM 23S — para análises métricas

# Datas padrão para coleta de imagens
SENTINEL2_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"
LANDSAT_COLLECTION = "LANDSAT/LC08/C02/T1_L2"
