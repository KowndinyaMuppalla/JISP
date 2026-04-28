# JISP — Jacobs Spatial Intelligence Platform

**Branch:** `feat/jisp-mvp`  
**Stack:** FastAPI · PostgreSQL/PostGIS/TimescaleDB · GeoServer · Ollama (llama3.2) · MapLibre GL

## Quick Start

```bash
# 1. Clone and switch to MVP branch
git clone https://github.com/KowndinyaMuppalla/JISP.git && cd JISP
git checkout feat/jisp-mvp

# 2. Copy env
cp .env .env.local  # edit if needed

# 3. Start full stack (GeoServer + Ollama + DB + API + UI)
docker compose -f docker/docker-compose.yml up -d

# 4. Wait ~3 min for Ollama to pull llama3.2 (~2GB)
docker logs jisp_ollama -f

# 5. Seed sample data (180 water assets across US/UK/ANZ/APAC)
docker compose -f docker/docker-compose.yml exec api python scripts/seed_sample_data.py

# 6. Configure GeoServer layers + VectorTiles
docker compose -f docker/docker-compose.yml exec api python scripts/setup_geoserver.py

# 7. Run GeoAI pipeline (scores all assets, builds inspection queue)
curl -X GET http://localhost:8000/api/v1/geoai/run-sync
```

## Access

| Service     | URL                              |
|-------------|----------------------------------|
| Web Map UI  | http://localhost:3000            |
| API Docs    | http://localhost:8000/docs       |
| GeoServer   | http://localhost:8080/geoserver  |
| Ollama      | http://localhost:11434           |

## API Endpoints

```
GET  /health
GET  /api/v1/assets?region=US&asset_class=PIPE_W&risk_tier=critical
GET  /api/v1/assets/{id}
POST /api/v1/assets
GET  /api/v1/assets/{id}/observations
GET  /api/v1/geoai/run-sync
GET  /api/v1/geoai/inspection-queue
GET  /api/v1/geoai/explain/{id}        ← LLM explanation via llama3.2
POST /api/v1/import/upload             ← ZIP/SHP/GPKG/GeoJSON
POST /api/v1/explain                   ← Manual explain (existing)
```

## Architecture

```
Data Sources (EPA/USGS/OS/BOM/LINZ/OSM/CSV)
    ↓ Ingestion Adapters (Python)
PostgreSQL + PostGIS + TimescaleDB
    ↓ GeoServer → Vector Tile PBF
MapLibre GL Web Map ← → FastAPI
    ↓                      ↓
Asset CRUD         GeoAI Pipeline
Risk Scoring       Anomaly Detection
Inspection Queue   SHAP Attribution
                   LLaMA 3.2 Explanation
```
