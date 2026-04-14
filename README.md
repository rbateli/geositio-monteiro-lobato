# GeoSítio — Inteligência Geoespacial Aplicada à Propriedade Rural

Projeto de portfólio que aplica **ciência de dados, IA e geotecnologia** a uma propriedade rural real em **Monteiro Lobato, SP**, transformando dados geoespaciais gratuitos em decisões práticas para gestão do sítio.

## O que este projeto faz

| Módulo | Descrição | Status |
|--------|-----------|--------|
| 01 — Mapeamento Interativo | Mapa com camadas de satélite, relevo e limites municipais | ✅ |
| 02 — Uso e Cobertura do Solo | Classificação de imagens com ML + séries NDVI | 🔜 |
| 03 — Aptidão Agrícola | Modelo preditivo para culturas adequadas | 🔜 |
| 04 — Monitoramento Ambiental | Detecção de tendências com séries temporais | 🔜 |
| 05 — Detecção de Mudanças | Comparação multitemporal de imagens | 🔜 |
| 06 — Dashboard | Painel web unificado com Streamlit | 🔜 |

## Stack

Python · GeoPandas · Rasterio · Folium · Scikit-learn · XGBoost · Prophet · Streamlit · Google Earth Engine

## Como rodar

```bash
# Criar ambiente virtual
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# Instalar dependências
pip install -r requirements.txt

# Rodar notebooks
jupyter notebook notebooks/
```

## Fontes de dados

- **Imagens de satélite:** Sentinel-2 (ESA), Landsat 8 (NASA/USGS)
- **Elevação:** SRTM 30m, ALOS PALSAR 12.5m
- **Vetoriais:** IBGE, CAR, MapBiomas
- **Clima:** INMET, NASA POWER

## Estrutura

```
notebooks/   → Jupyter notebooks por módulo
src/         → Módulos Python reutilizáveis
dashboard/   → Aplicação Streamlit
data/        → Apenas amostras leves (dados pesados ficam locais)
docs/        → Metodologia e documentação
```

## Autor

Projeto de portfólio em Ciência de Dados e IA aplicada a geotecnologia.
