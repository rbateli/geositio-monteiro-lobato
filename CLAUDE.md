# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**GeoSítio** — Inteligência Geoespacial Aplicada à Propriedade Rural. A data science and AI portfolio project that applies geotechnology to a real rural property in Monteiro Lobato, SP, Brazil. The project collects, processes, analyzes, and visualizes geographic data using satellite imagery, elevation models, climate data, and vector datasets.

## Tech Stack

- **Language:** Python 3.10+
- **Geospatial:** rasterio, geopandas, shapely, folium, leafmap, earthengine-api
- **ML/AI:** scikit-learn, xgboost, tensorflow or pytorch
- **Time Series:** Prophet, LSTM models
- **Dashboard:** Streamlit or Dash
- **Data Sources:** Sentinel-2, Landsat, SRTM, ALOS PALSAR, IBGE, MapBiomas, CAR, INMET, NASA POWER

## Project Modules

1. **Mapeamento interativo** — property delimitation, interactive maps with relief/hydrography/vegetation layers
2. **Uso e cobertura do solo** — satellite image classification (Random Forest/CNN), NDVI time series
3. **Aptidão agrícola** — predictive model crossing soil, slope, climate, and vegetation data
4. **Monitoramento ambiental** — time series analysis for degradation/recovery detection
5. **Detecção de mudanças** — multi-temporal change detection
6. **Dashboard** — unified web panel with maps, charts, alerts, and predictions

## Project Structure

```
notebooks/       # Jupyter notebooks (numbered by module)
src/             # Reusable Python modules (pipeline, geo utils, ML models)
dashboard/       # Streamlit/Dash application
data/            # Sample/lightweight data only (heavy data stays external)
docs/            # Methodology and documentation
```

## Conventions

- All code, comments, and documentation in Portuguese (Brazilian) unless referencing library APIs
- Notebooks are prefixed with number indicating module order (e.g., `01_coleta_dados.ipynb`)
- Heavy geospatial data (rasters, large shapefiles) must NOT be committed — use `.gitignore` and document download instructions
- Coordinate reference system: EPSG:4326 (WGS84) for display, EPSG:31983 (SIRGAS 2000 / UTM zone 23S) for analysis in the Monteiro Lobato region
