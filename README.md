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
- **Explainability & Reasoning**: SHAP, Ollama, Llama 3.3
- **APIs**: FastAPI, Pydantic
- **Visualization**: MapLibre GL JS, Streamlit
- **Containerization (local only)**: Docker, Docker Compose, Docker Desktop

## Repository Layout

See the top-level folders for the canonical structure. Each folder has a single, strict responsibility (see `docs/architecture/solution-architecture.md`).

## Status

Scaffold only. See `docs/adr/001-standalone-ai-first.md` for core architectural decisions.

## Run the management demo (Streamlit)

A self-contained demo dashboard showcases the reasoning layer end-to-end using
seeded assets. No database or ingestion required — the UI calls the live
`/explain` endpoint and displays a LLaMA 3.3 explanation on a map.

```bash
# 1. Install deps (once)
pip install -r requirements.txt

# 2. Start the API (needs Ollama running with llama3.3 pulled)
uvicorn api.main:app --host 0.0.0.0 --port 8000

# 3. In a second terminal, launch the dashboard
./scripts/run_demo_ui.sh
#   then open http://localhost:8501
```

Click a finding in the sidebar, hit **Explain with LLaMA 3.3**, and the map +
explanation panel update with a real observational narrative. See
`ui/dashboards/` for the demo source and `MVP_TASKS.md` for what else is
needed to replace the seeded data with a real ingestion-and-detection pipeline.
