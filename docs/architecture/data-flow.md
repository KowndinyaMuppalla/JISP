# JISP Data Flow

> Status: placeholder — to be populated in later steps.

High-level flow (pre-field only):

1. `ingestion/` pulls and normalizes regional sources (US: USGS, EPA;
   ANZ: BoM, EA) and imagery (e.g. Sentinel-2).
2. `spatial/` persists assets and geometries into PostgreSQL + PostGIS.
3. `timeseries/` persists time-series observations into TimescaleDB.
4. `geoai/` computes spatial/temporal features, runs change detection and
   risk models.
5. `reasoning/` turns model outputs into human-readable explanations
   using Ollama + Kimi.
6. `api/` exposes FastAPI endpoints consumed by `ui/` dashboards and maps.
