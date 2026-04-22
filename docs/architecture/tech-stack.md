# JISP Technology Stack (Approved — Non-Negotiable)

> Status: source-of-truth summary.

## Language

- Python

## Spatial & Time-Series Core

- PostgreSQL
- PostGIS
- TimescaleDB

## Geospatial Processing

- GDAL / OGR
- GeoPandas
- Rasterio
- xarray

## GeoAI

- scikit-learn
- PySAL
- HDBSCAN / DBSCAN
- OpenGeoAI (where applicable)
- OpenCL (via PyOpenCL or Numba)

## Explainability & Reasoning

- SHAP
- Ollama
- Kimi LLM

## APIs

- FastAPI
- Pydantic

## Visualization

- MapLibre GL JS
- Streamlit

## Containerization (local only)

- Docker
- Docker Compose
- Docker Desktop

## GPU

- NVIDIA Container Toolkit (when NVIDIA GPU present)
- Ollama MUST run with GPU enabled
- GeoAI containers MUST be GPU-capable
- CPU-only execution avoided where GPU is available

**No other tools, cloud services, or frameworks are permitted.**
