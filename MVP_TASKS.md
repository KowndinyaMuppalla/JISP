# JISP — MVP Task List

**Goal:** a workable end-to-end MVP where a real GeoAI finding, derived from real ingested data against a persisted asset, flows through the API, is explained by LLaMA 3.3, is audited, and is viewable in the UI.

**Status today (2026-04-23):** Steps 1–5 complete — Reasoning (Ollama + LLaMA 3.3), API (`/health`, `/explain`), GeoAI output contract, audit logging, safety guards. Everything else (`ingestion/`, `spatial/db`, `timeseries/`, `geoai/*`, `ui/`) is placeholder shape only (`NotImplementedError` / empty SQL / `.gitkeep`).

---

## MVP Definition (acceptance criteria)

An operator can:
1. Run `docker compose up` and get Postgres+PostGIS+TimescaleDB, Ollama, and the JISP API online.
2. Load at least one real asset + one real data source (one US or ANZ ingestor, one Sentinel‑2 raster).
3. Trigger one GeoAI detection (flood‑change **or** anomaly) against that asset.
4. Receive a LLaMA 3.3 explanation via `/explain`.
5. See the finding + explanation on a map in the Streamlit/MapLibre UI.
6. Retrieve the audit record for that explanation.

Anything beyond this is post‑MVP.

---

## Task List

Legend: **[P0]** = MVP‑blocking, **[P1]** = MVP‑quality (needed for demo), **[P2]** = post‑MVP.

### 1. Infrastructure & Environment

- [ ] **[P0] Bring up Postgres + PostGIS + TimescaleDB in compose** — add a `db` service to `docker/docker-compose.yml`, wire `JISP_DB_*` env from `.env.example`, mount a volume, add healthcheck. Verify `config/database.py` connects.
- [ ] **[P0] Pin Ollama model bootstrap** — extend compose to `ollama pull llama3.3` on first start (init container or entrypoint) so `/explain` works out of the box.
- [ ] **[P1] API image + hot‑reload dev mode** — confirm `docker/Dockerfile.api` runs uvicorn, mounts source in dev.
- [ ] **[P1] One‑command bootstrap script** — `scripts/dev_up.sh`: compose up → wait for DB healthy → run migrations → seed demo asset.
- [ ] **[P2] GPU profile** for Ollama (already scaffolded in Step 4 docs) kept optional.

### 2. Spatial Layer (PostGIS)

- [ ] **[P0] Write real DDL in `spatial/db/schema.sql`** — `assets` table (id, type, geometry(Geometry, 4326), attributes JSONB, created_at), plus indexes (GIST on geometry, btree on type).
- [ ] **[P0] Enable extensions** in `spatial/db/extensions.sql` — `postgis`, `timescaledb`, `pg_trgm` as needed.
- [ ] **[P0] Migration runner** — a thin `scripts/migrate.py` (or Alembic init) that applies `extensions.sql` then `schema.sql` then files under `spatial/db/migrations/`.
- [ ] **[P0] Implement `spatial/assets/asset_repository.py`** — `insert`, `get_by_id`, `list_by_bbox(wkt)`, `nearest(wkt, k)`. Uses SQLAlchemy session from `config/database.py`.
- [ ] **[P1] `spatial/geometry/spatial_utils.py`** — WKT ↔ shapely helpers, buffer, distance, reproject (4326 ↔ source CRS). Thin wrapper over shapely/pyproj; no DB calls.
- [ ] **[P1] `spatial/networks/hydrology.py`** — minimal: load flood-zone polygons (seeded) and expose `intersects_flood_zone(asset_geom)`.
- [ ] **[P2] Versioned migrations** (Alembic) once schema starts evolving.

### 3. Timeseries Layer (TimescaleDB)

- [ ] **[P0] Hypertable DDL** — add `timeseries/db/schema.sql` (new) defining a `sensor_readings(asset_id, metric, ts, value, unit)` table + `create_hypertable('sensor_readings','ts')`. Hook into migration runner.
- [ ] **[P0] Implement `timeseries/ingestion.py`** — `insert_readings(rows)` batch insert.
- [ ] **[P0] Implement `timeseries/queries.py`** — `latest(asset_id, metric)`, `window(asset_id, metric, start, end)`, `rolling_stats(...)` used by anomaly detection.
- [ ] **[P1] Retention / compression policy** on `sensor_readings` (optional for MVP, but one‑liner with Timescale).

### 4. Ingestion Layer

Pick the **minimum** ingestors needed for one end‑to‑end demo. Recommended MVP set: **one US source** (USGS streamflow), **one ANZ source** (BoM rainfall), **one imagery source** (Sentinel‑2 scene for a single AOI).

- [ ] **[P0] Implement `BaseIngestor.run()`** (currently `NotImplementedError`) — calls `fetch()` then `normalize()` and returns `IngestionResult`. Keep it boring.
- [ ] **[P0] `ingestion/us/usgs_ingestor.py`** — pull a station's streamflow for a date range → normalized records {asset_id, metric:"streamflow_cfs", ts, value}. Land rows via `timeseries/ingestion.py`. Keep creds out of code.
- [ ] **[P0] `ingestion/anz/bom_ingestor.py`** — rainfall from BoM for a station → normalized {metric:"rainfall_mm", ts, value}.
- [ ] **[P0] `ingestion/imagery/sentinel2_ingestor.py`** — download one scene for a bbox/date → store COG path + metadata in a `raster_catalog` table (add to schema). No full pipeline — MVP only needs "before" and "after" scenes for flood change.
- [ ] **[P1] `ingestion/us/epa_ingestor.py`** and **`ingestion/anz/ea_ingestor.py`** — deferred unless demo AOI needs them.
- [ ] **[P1] A CLI wrapper** (`scripts/ingest.py <source> [--start --end --aoi]`) so operators can ingest without touching Python.
- [ ] **[P2] Scheduler / cron** — out of MVP; ingestion is manual.

### 5. GeoAI Layer (detection logic)

All files exist in shape only and raise `NotImplementedError`. MVP requires **two** working detectors.

- [ ] **[P0] `geoai/features/temporal_features.py`** — rolling mean/std, z-score from a timeseries window.
- [ ] **[P0] `geoai/features/spatial_features.py`** — distance-to-nearest-hazard, intersection-area; uses shapely (NOT spatial/ repo — load inputs via caller).
- [ ] **[P0] `geoai/inspections/anomaly_detection.py::detect(asset_id, metric)`** — pull a window from `timeseries.queries`, compute z-score, if over threshold return `AnomalyDetection(subject=asset_id, template="anomaly_summary", context={...})`. Observational only — no prediction.
- [ ] **[P0] `geoai/inspections/flood_change.py::detect(asset_id)`** — given two Sentinel‑2 scenes (from raster_catalog), compute NDWI delta over asset buffer, return `FloodChangeDetection`. OK to start with a naive NDWI threshold; improve later.
- [ ] **[P1] `geoai/inspections/erosion_detection.py`** — same pattern with NDVI; optional for MVP.
- [ ] **[P1] `geoai/models/clustering.py`** — HDBSCAN over asset attributes; post‑MVP unless the demo story needs it.
- [ ] **[P1] `geoai/models/risk_models.py`** — **clarify scope before building**: current product stance is "no prediction, no scoring." Likely remove or rename to `proximity_metrics.py`.
- [ ] **[P1] `geoai/explainability/shap_explainer.py`** — only meaningful once a real model exists. Defer.

### 6. API Layer

- [ ] **[P0] `POST /detect/flood-change`** — route calling `geoai.inspections.flood_change.detect(asset_id)` then forwarding to `reasoning_service.explain(...)`. Returns `ExplainResponse` + the finding. (Pattern A composition belongs in `api/`, not in `geoai/`.)
- [ ] **[P0] `POST /detect/anomaly`** — same, for `anomaly_detection.detect(asset_id, metric)`.
- [ ] **[P0] `GET /assets/{id}`** — reads from `spatial/assets/asset_repository`. Needed so the UI has something to render.
- [ ] **[P0] `GET /assets?bbox=...`** — list assets in a bbox for the map.
- [ ] **[P0] Wire audit writes** — every `/explain` and `/detect/*` call persists a row via `logging_audit/audit_service`. (Step 5 infra exists; hook it into the new routes.)
- [ ] **[P1] `GET /audit/explanations/{id}`** — retrieve a past explanation. Makes the audit trail demoable.
- [ ] **[P1] Error envelope consistency** — ensure 400/422/503 shapes match `API_SPEC.md`.

### 7. UI Layer

- [ ] **[P0] `ui/dashboards/streamlit_app.py`** — single page: bbox input → calls `GET /assets?bbox` → lists assets → "Run flood‑change" and "Run anomaly" buttons → calls the `/detect/*` endpoints → shows the explanation text.
- [ ] **[P0] MapLibre panel in `ui/maps/maplibre/`** — render the bbox + assets + flood polygon. Can be an `st.components.v1.html` MapLibre embed for MVP; full SPA is post‑MVP.
- [ ] **[P1] Explanation audit viewer** — dropdown of recent explanations, click to see the stored LLaMA output.
- [ ] **[P2] Auth** on the UI — out of MVP (local Docker only).

### 8. Tests & CI

- [ ] **[P0] Integration test `tests/test_end_to_end_mvp.py`** — spin up DB via testcontainers (or mark as requires-compose), seed 1 asset, seed fake timeseries, run `/detect/anomaly`, assert explanation text non-empty and audit row written. Ollama is the one external dep; gate with an `@pytest.mark.live_ollama` marker.
- [ ] **[P0] Unit tests for each new module** — ingestion normalizers, feature functions, repo CRUD. Aim at behavior, not mocks of everything.
- [ ] **[P1] GitHub Actions workflow** — lint (ruff), type (mypy, scoped), pytest unit tier on PR; skip live_ollama tier.
- [ ] **[P2] Coverage floor** — defer until MVP stabilizes.

### 9. Documentation

- [ ] **[P0] `docs/architecture/data-flow.md`** — fill in: ingest → persist → detect → explain → audit. Currently a placeholder.
- [ ] **[P0] `README.md` "Run the MVP in 5 minutes"** section — compose up, ingest sample, hit the UI.
- [ ] **[P1] `docs/data-model/core-entities.md`** — update to match the real DDL once Section 2 lands.
- [ ] **[P1] ADR for the Pattern‑A composition boundary** — lock in that `api/` composes, `geoai/` never imports reasoning. (ADR 001 exists; consider a follow‑up ADR for detect‑then‑explain routes.)

### 10. Hardening (MVP‑quality, not MVP‑blocking)

- [ ] **[P1]** Seed script with 5 realistic assets + one AOI + two Sentinel‑2 scenes so every first‑run demo is non‑empty.
- [ ] **[P1]** Structured logging config from `config/logging.yaml` actually loaded in `api/main.py`.
- [ ] **[P1]** `/health` upgraded to check DB + Ollama, not just app liveness.
- [ ] **[P2]** Rate limiting, API keys, CORS policy tightening.
- [ ] **[P2]** Streaming responses, batch `/explain`, caching — explicitly deferred in Step 4 notes.

---

## Suggested order of execution

1. **Section 1 + 2** (infra + PostGIS schema + repo) — nothing else runs without these.
2. **Section 3** (timeseries DDL + queries) — needed by anomaly detection.
3. **Section 4** — one US ingestor + one Sentinel‑2 ingestor is enough to unblock both detectors.
4. **Section 5** — anomaly detector first (smaller surface), then flood‑change.
5. **Section 6** — `/detect/*` and `/assets` routes wired to audit.
6. **Section 7** — Streamlit page is the demo vehicle.
7. **Section 8 + 9** — end‑to‑end test + README walkthrough close the loop.

Rough size estimate, solo dev: ~2–3 weeks to P0 complete, assuming the Postgres/Timescale and imagery pieces don't surface surprises.

---

## Out of scope for MVP (explicit)

- Field execution / offline‑first (ADR 001).
- Prediction, scoring, recommendations (enforced at template, schema, and service layers).
- Multi‑tenant auth.
- Horizontal scaling / k8s.
- Data warehouse / BI exports.
