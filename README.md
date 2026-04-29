# JISP — Jacobs Spatial Intelligence Platform

> **Pre-field · AI-first · Geospatial-native · Explainable by design**

JISP is a proof-of-concept platform that combines spatial data management, ML-driven risk
scoring, and local LLM reasoning to help infrastructure operations teams make better
pre-field decisions. It is scoped to water-network assets across five global regions (US,
UK, Australia, New Zealand, Asia-Pacific) but the architecture generalises to any asset
class or domain.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full solution design.

---

## Capabilities at a glance

| Capability | Detail |
|---|---|
| **Live map** | MapLibre GL JS canvas with risk-coloured point / line / polygon layers |
| **Risk visualisation** | Per-asset `risk_score` (0–1) drives a colour ramp (green → amber → red) |
| **Hierarchical layer panel** | Region → asset-class tree; click a class to list individual assets |
| **Asset detail** | Right-rail panel: attributes, risk bar, SHAP driver bars, LLM explanation |
| **GeoAI pipeline** | Batch risk scoring + z-score / rolling-drop anomaly detection |
| **Explainability** | Local llama3.2 via Ollama — observational narrative only (no prediction) |
| **Time-series** | TimescaleDB `observations` table; sparkline in asset panel |
| **Import** | Drag-and-drop GeoPackage / Shapefile ZIP / GeoJSON → PostGIS via GeoPandas |
| **Search** | Instant asset-code / name search across all loaded regions |
| **Mock mode** | Full UI works with zero backend — in-memory GeoJSON for demos |

---

## Quick start

### Option A — Mock mode (zero backend)

```bash
cd JISP
python -m http.server 5500
# Open: http://localhost:5500
```

The app detects no backend and falls back to in-memory mock data automatically.
The status bar shows **MOCK API**.

---

### Option B — Full live stack (Docker)

**Prerequisites:** Docker Desktop with WSL 2 integration, ≥ 8 GB RAM available.

```bash
# 1. Copy env template
cp .env.example .env          # edit credentials if needed

# 2. Start all five services
cd docker
docker compose up -d

# 3. Wait ~60 s for DB health, then ~3 min for Ollama to pull llama3.2 (~2 GB)
docker compose ps             # all should show healthy

# 4. Seed sample data (180 water assets across US/UK/ANZ/APAC)
docker compose exec api python scripts/seed_sample_data.py

# 5. Configure GeoServer layers + vector tiles
docker compose exec api python scripts/setup_geoserver.py

# 6. Run the GeoAI pipeline (score all assets, build inspection queue)
curl -X GET http://localhost:8000/api/v1/geoai/run-sync

# 7. Open the UI
# Via Nginx container → http://localhost:3000
# Via Python dev server → http://localhost:5500  (index.html targets :8000 automatically)
```

When the backend is healthy and `/api/v1/assets` returns a GeoJSON FeatureCollection,
the status bar switches to **LIVE API** and the model badge shows **llama3.3 · live**.

---

## Service URLs

| Service | URL |
|---|---|
| Frontend (Nginx) | http://localhost:3000 |
| Frontend (dev server) | http://localhost:5500 |
| FastAPI — Swagger UI | http://localhost:8000/docs |
| FastAPI — ReDoc | http://localhost:8000/redoc |
| GeoServer admin | http://localhost:8080/geoserver |
| Ollama API | http://localhost:11434 |
| PostgreSQL | localhost:5432 (user: `jisp`, db: `jisp`) |

---

## Tech stack

### Frontend

| Layer | Technology |
|---|---|
| Map canvas | MapLibre GL JS 4.7.1 (loaded via CDN) |
| Basemap | CARTO Positron raster tiles (CORS-safe, no API key) |
| UI components | Vanilla ES modules — no bundler, no framework |
| Type safety | JSDoc annotations + VS Code / tsserver |
| Dev server | `python -m http.server` (mock) or Nginx container (live) |

### Backend

| Layer | Technology |
|---|---|
| API framework | FastAPI 0.111 + Uvicorn (async, hot-reload in dev) |
| Spatial database | PostgreSQL 15 + PostGIS 3 + TimescaleDB |
| Map server | GeoServer 2.24.2 with vector-tiles plugin |
| LLM inference | Ollama — llama3.2 (runs fully local, air-gap capable) |
| GIS ingestion | GeoPandas + asyncpg |
| Containerisation | Docker Compose (5 services, bridge network `jisp_net`) |

---

## Project structure

```
JISP/
├── index.html                    # SPA shell + JISP_CONFIG runtime config
├── src/
│   ├── main.js                   # Bootstrap: wires all components + KPI strip
│   ├── map.js                    # JispMap: MapLibre setup, layers, interactions
│   ├── api/
│   │   ├── client.js             # ApiClient — auto/live/mock + resilient fallbacks
│   │   ├── mocks.js              # In-memory mock for every API endpoint
│   │   └── types.js              # JSDoc type definitions (mirrors Pydantic schemas)
│   ├── panels/
│   │   ├── layer-panel.js        # Left rail: tree-view, overlays, collapse
│   │   ├── tree-view.js          # Region → class → asset hierarchy component
│   │   ├── asset-panel.js        # Right rail: attributes, risk, explanation
│   │   ├── import-panel.js       # Drag-and-drop import modal
│   │   └── search.js             # Top-bar asset search
│   ├── styles/
│   │   ├── tokens.css            # Design tokens (colour, spacing, type scale)
│   │   ├── layout.css            # Full-bleed map, rails, status bar
│   │   ├── panels.css            # Panel, toggle, KPI, risk-card, explain-block
│   │   ├── tree-view.css         # Tree-view component styles
│   │   └── map.css               # Popup, loading overlay, credits
│   └── util/
│       ├── dom.js                # $() selector + el() element factory
│       └── format.js             # fmtLonLat, fmtDate helpers
├── src/data/                     # GeoJSON fixtures for mock mode
│   ├── sample-assets.geojson
│   ├── sample-cluster-zones.geojson
│   └── sample-explain.json
├── api/                          # FastAPI application
│   ├── main.py                   # App factory, CORS, router registration
│   ├── schemas/payloads.py       # Pydantic request/response models
│   └── routes/
│       ├── assets.py             # CRUD + spatial query for assets
│       ├── geoai.py              # Risk pipeline, inspection queue, explain
│       ├── reasoning.py          # POST /explain — LLM explanation endpoint
│       ├── timeseries.py         # Observations GET/POST + latest readings
│       └── upload.py             # File ingestion: SHP ZIP / GPKG / GeoJSON
├── reasoning/
│   ├── reasoning_service.py      # Template loader + Ollama orchestration
│   ├── ollama_client.py          # HTTP client with exponential-backoff retry
│   └── prompt_templates/         # asset_risk.txt, flood_explanation.txt, anomaly_summary.txt
├── spatial/
│   └── db/
│       ├── schema.sql            # PostGIS schema (auto-loaded by Docker init)
│       └── migrations/           # Reference tables, indexes
├── docker/
│   ├── docker-compose.yml        # 5-service stack definition
│   └── api.Dockerfile            # FastAPI container image
└── .env.example                  # Environment variable template
```

---

## API reference

Full interactive docs: **http://localhost:8000/docs**

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness probe — returns `{"status":"ok"}` |
| `GET` | `/api/v1/assets` | List assets (params: `region`, `asset_class`, `bbox`, `risk_tier`, `limit`, `offset`) |
| `GET` | `/api/v1/assets/{id}` | Single asset with geometry + latest risk score |
| `POST` | `/api/v1/assets` | Create asset |
| `GET` | `/api/v1/assets/{id}/observations` | Time-series readings (`metric`, `from`, `to`) |
| `POST` | `/api/v1/assets/{id}/observations` | Ingest a sensor reading |
| `GET` | `/api/v1/assets/{id}/latest` | Latest reading per metric |
| `POST` | `/api/v1/explain` | LLM explanation for a GeoAI finding (templates: `asset_risk`, `flood_explanation`, `anomaly_summary`) |
| `POST` | `/api/v1/geoai/run` | Trigger full risk-score + anomaly pipeline (async, background task) |
| `GET` | `/api/v1/geoai/run-sync` | Same pipeline, synchronous — waits for completion |
| `GET` | `/api/v1/geoai/inspection-queue` | Ranked pre-field inspection queue |
| `GET` | `/api/v1/geoai/explain/{asset_id}` | Per-asset GeoAI narrative (logged to `explanation_log`) |
| `POST` | `/api/v1/import/upload` | Ingest GeoPackage / Shapefile ZIP / GeoJSON |

---

## Configuration

### Frontend

`window.JISP_CONFIG` in `index.html` controls the API target:

```html
<script>
  window.JISP_CONFIG = {
    apiBaseUrl: "http://localhost:8000",   // FastAPI base URL
    apiMode:    "auto"                     // "auto" | "live" | "mock"
  };
</script>
```

| `apiMode` | Behaviour |
|---|---|
| `auto` | Probes `GET /api/v1/assets?limit=1`; uses live if response is valid GeoJSON FeatureCollection, else mocks |
| `live` | Always calls the real backend (no probe) |
| `mock` | Always uses in-memory mocks |

### Backend (`.env`)

```bash
DATABASE_URL=postgresql://jisp:jisp_secret@localhost:5432/jisp
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.2
OLLAMA_TIMEOUT=120
GEOSERVER_URL=http://localhost:8080/geoserver
GEOSERVER_USER=admin
GEOSERVER_PASS=geoserver
LOG_LEVEL=INFO
```

---

## Known MVP gaps

| Area | Current state | Required fix |
|---|---|---|
| **API response shape** | `GET /api/v1/assets` returns `{"count":N,"assets":[...]}` | Return `{"type":"FeatureCollection","features":[...]}` to enable live mode |
| **Auth** | No authentication on any endpoint | Add JWT or API-key middleware before any external exposure |
| **GeoServer wiring** | GeoServer deployed but not connected to frontend map layers | Add WMS / MVT source in `map.js` once layers are published |
| **DB seed script** | No committed seed; mock GeoJSON is the demo data source | Commit `spatial/db/seed.py` with synthetic water-network data |
| **WebSocket stream** | Mock falls back to 4 s polling | Implement real `WS /ws/assets/{id}/stream` in FastAPI |
| **LLM templates** | Three templates only | Add `cluster_hotspot`, `inspection_brief` |
| **Mobile layout** | Optimised for 1280px+ desktop | Responsive breakpoints for tablet field use |

---

## Development notes

- **No build step.** All JS is native ES modules served directly. Bump the `?v=N` cache-buster
  on every `<link>` and `<script>` in `index.html` when you ship a change.
- **Type checking.** Run `tsc --noEmit --allowJs --checkJs --target ESNext` to surface JSDoc errors.
- **Formatter warning.** Some editors inject stray `;` before class method braces (`mount() ;{`),
  breaking runtime parsing. Disable auto-format on save for `src/panels/*.js` if you see this.
- **Ollama cold-start.** First inference after `docker compose up` can take 20–40 s while
  llama3.2 loads into memory. Subsequent calls respond in 1–3 s.

---

## Licence

Internal Jacobs PoC — not for public distribution.
