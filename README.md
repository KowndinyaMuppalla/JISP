# JISP – Jacobs Spatial Intelligence Platform

JISP is a pre-field, cloud-native spatial intelligence platform.

## Positioning

- **Pre-field**: used BEFORE field execution to provide intelligence, prioritization, and reasoning.
- **Cloud-native**: designed to run on standard containerized infrastructure.
- **Standalone**: not a field execution system, not an offline-first platform (core), not a mobile backend, not a data warehouse.

## What JISP Is

- AI-first
- Geospatial-native
- Asset-centric
- Time-aware
- Explainable by design

## What JISP Is Not

- A field execution system
- An offline-first platform (core)
- A mobile backend
- A data warehouse
- A vendor-locked solution

> Offline-first capability is a **future extension only**. It must be possible to add later without modifying the JISP core.

## Approved Technology Stack

- **Language**: Python
- **Spatial & Time-Series Core**: PostgreSQL, PostGIS, TimescaleDB
- **Geospatial Processing**: GDAL/OGR, GeoPandas, Rasterio, xarray
- **GeoAI**: scikit-learn, PySAL, HDBSCAN/DBSCAN, OpenGeoAI, OpenCL (via PyOpenCL or Numba)
- **Explainability & Reasoning**: SHAP, Ollama, Kimi LLM
- **APIs**: FastAPI, Pydantic
- **Visualization**: MapLibre GL JS, Streamlit
- **Containerization (local only)**: Docker, Docker Compose, Docker Desktop

## Repository Layout

See the top-level folders for the canonical structure. Each folder has a single, strict responsibility (see `docs/architecture/solution-architecture.md`).

## Status

Scaffold only. See `docs/adr/001-standalone-ai-first.md` for core architectural decisions.
