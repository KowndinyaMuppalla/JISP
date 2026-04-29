# JISP — Solution Architecture

> Jacobs Spatial Intelligence Platform · MVP v0.1

---

## 1. System context

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Field Operations User                        │
│          (desktop browser / future: tablet in the field)            │
└─────────────────────────────┬───────────────────────────────────────┘
                              │  HTTPS (SPA — no page reloads)
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         JISP Web UI                                 │
│   MapLibre GL JS · Vanilla ES Modules · No bundler / no framework   │
│   Served by: Nginx :3000 (prod) | python http.server :5500 (dev)    │
└────────┬────────────────────────────────────────┬───────────────────┘
         │ REST + JSON                            │ WMS / MVT tiles
         ▼                                        ▼
┌────────────────────┐                 ┌──────────────────────┐
│   FastAPI :8000    │                 │  GeoServer :8080     │
│   (Uvicorn async)  │                 │  (future map layers) │
└────────┬───────────┘                 └──────────────────────┘
         │                                        │
         ├──── asyncpg ────────────────────────────┤
         ▼                                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│               PostgreSQL 15 + PostGIS 3 + TimescaleDB               │
│      assets · risk_scores · observations · inspection_queue         │
│      asset_alerts · explanation_log · cluster_zones                 │
└─────────────────────────────────────────────────────────────────────┘
         │
         │ HTTP (urllib / streaming)
         ▼
┌──────────────────────┐
│    Ollama :11434     │
│    llama3.2 (local)  │
│    Air-gap capable   │
└──────────────────────┘
```

All five services run on a single Docker Compose `bridge` network (`jisp_net`).
No external internet access is required after the initial `docker compose up`
pull (Ollama model download aside).

---

## 2. Docker service topology

| Service | Image | Port(s) | Role |
|---|---|---|---|
| `jisp_db` | `timescale/timescaledb-ha:pg15-latest` | 5432 | Spatial + time-series database |
| `jisp_geoserver` | `kartoza/geoserver:2.24.2` | 8080 | OGC map server (WMS, WFS, MVT) |
| `jisp_ollama` | `ollama/ollama:latest` | 11434 | Local LLM inference (llama3.2) |
| `jisp_api` | `docker/api.Dockerfile` | 8000 | FastAPI — REST API + GeoAI pipeline |
| `jisp_ui` | `nginx:alpine` | 3000 | Static frontend (for containerised demo) |

**Startup order:** `db` (healthy) → `geoserver` + `api` in parallel → `ui`

**Volumes:**
- `pgdata` — PostgreSQL WAL + data files (survives container restarts)
- `geoserver_data` — GeoServer workspace / layer configs
- `ollama_models` — Downloaded model weights (~2 GB for llama3.2)

---

## 3. Frontend architecture

```
index.html
  └─ <script type="module" src="src/main.js">  ← entry point
       ├─ ApiClient              (src/api/client.js)
       │    ├─ auto-probe        → GET /api/v1/assets?limit=1
       │    ├─ live mode         → real fetch calls
       │    └─ mock mode         → in-memory GeoJSON (src/api/mocks.js)
       │
       ├─ JispMap                (src/map.js)
       │    ├─ loadMaplibre()    → poll window.maplibregl (CDN)
       │    ├─ BASEMAP_STYLE     → CARTO Positron raster tiles
       │    ├─ Sources           → "assets" (GeoJSON), "cluster-zones" (GeoJSON)
       │    └─ Layers (bottom→top)
       │         cluster-zones-fill / cluster-zones-line
       │         asset-polygon-fill / asset-polygon-outline
       │         asset-line-casing / asset-line
       │         asset-point-halo / asset-point
       │         asset-point-selected / asset-line-selected
       │
       ├─ LayerPanel             (src/panels/layer-panel.js)
       │    └─ TreeView          (src/panels/tree-view.js)
       │         ├─ Section 1    Region header + grouped class rows
       │         └─ Section 2   Individual asset list (click-to-fly)
       │
       ├─ AssetPanel             (src/panels/asset-panel.js)
       │    ├─ Attributes DL     key-value pairs from feature.properties
       │    ├─ Risk card         score bar + condition class badge
       │    ├─ SHAP bars         top driver visualisation
       │    └─ Explain block     POST /explain → streamed LLM text
       │
       ├─ ImportPanel            (src/panels/import-panel.js)
       │    └─ Dropzone          POST /api/v1/import/upload (multipart)
       │
       └─ SearchBox              (src/panels/search.js)
            └─ Debounced input   GET /api/v1/assets/search?q=
```

### API client mode selection

```
window.JISP_CONFIG.apiMode
  │
  ├─ "mock"  ──────────────────────────────► mocks.js (always)
  │
  ├─ "live"  ──────────────────────────────► real fetch (always)
  │
  └─ "auto"  → probe GET /api/v1/assets?limit=1
               │
               ├─ HTTP OK + { features: [...] }  ──► live mode
               │
               └─ timeout / error / wrong shape  ──► mock fallback
                    (every method has try/catch fallback to mock)
```

### Map layer paint expressions

All risk-coloured layers share one interpolate expression:

```js
["interpolate", ["linear"], ["coalesce", ["get", "risk_score"], 0],
  0.0, "#2ec27e",   // green  — low risk
  0.4, "#e6c84a",   // amber  — moderate
  0.6, "#f08a3c",   // orange — elevated
  0.8, "#e64545"    // red    — high risk
]
```

Selection is driven by two additional layers (`asset-point-selected`,
`asset-line-selected`) that are filtered to `["==", ["id"], selectedId]`
and painted in `#0066FF`.

---

## 4. Backend architecture

### FastAPI route map

```
api/main.py
  ├─ /health                       GET  — liveness
  ├─ /api/v1/assets                GET  — list (filter: region, class, bbox, risk_tier)
  ├─ /api/v1/assets                POST — create
  ├─ /api/v1/assets/{id}           GET  — single asset + geometry + risk
  ├─ /api/v1/assets/{id}/geojson   GET  — GeoJSON feature
  ├─ /api/v1/assets/{id}/observations  GET/POST — time-series
  ├─ /api/v1/assets/{id}/latest    GET  — latest reading per metric
  ├─ /api/v1/explain               POST — LLM explanation (reasoning layer)
  ├─ /api/v1/geoai/run             POST — async pipeline trigger
  ├─ /api/v1/geoai/run-sync        GET  — sync pipeline (blocks until done)
  ├─ /api/v1/geoai/inspection-queue GET — ranked queue
  ├─ /api/v1/geoai/explain/{id}    GET  — per-asset GeoAI narrative
  └─ /api/v1/import/upload         POST — GIS file ingestion
```

### GeoAI pipeline (`/api/v1/geoai/run`)

```
POST /api/v1/geoai/run
  │
  ├─ 1. Fetch all active assets from DB
  │
  ├─ 2. score_assets_batch()         geoai/models/risk_models.py
  │       ├─ feature engineering     (age, material, condition, criticality…)
  │       ├─ XGBoost / rule model    → risk_score [0–1], risk_tier
  │       └─ SHAP attribution        → shap_values dict
  │
  ├─ 3. Anomaly detection            geoai/inspections/anomaly_detection.py
  │       ├─ detect_zscore()         flag if value > μ ± 3σ
  │       └─ detect_rolling_drop()   flag if rolling mean drops > threshold
  │
  ├─ 4. Write to DB (transaction)
  │       ├─ INSERT risk_scores      (score, tier, SHAP, anomaly_flag)
  │       ├─ UPDATE assets.risk_tier
  │       └─ INSERT asset_alerts     (for each detected anomaly)
  │
  └─ 5. Rebuild inspection_queue
          ├─ DELETE pending rows
          └─ INSERT ranked by risk_score DESC + anomaly_flag
```

### Reasoning layer

```
POST /api/v1/explain  { subject, template, context }
  │
  ├─ reasoning_service.explain()
  │     ├─ _load_template(name)      read .txt from prompt_templates/
  │     ├─ _render_context(context)  JSON-serialise the GeoAI context dict
  │     └─ prompt = template.format(subject=..., context=...)
  │
  ├─ ollama_client.generate(prompt)
  │     ├─ POST http://ollama:11434/api/generate
  │     ├─ stream: false
  │     └─ exponential backoff (3 retries: 1s, 2s, 4s)
  │
  └─ return Explanation(subject, template, model, explanation)
```

**Constraint:** The reasoning layer is strictly observational. Templates are authored
to produce factual descriptions of detected signals. No predictions, no risk scores,
no recommendations are emitted by the LLM. This is enforced by prompt design and
validated by the `ExplainResponse` Pydantic schema.

### Supported explanation templates

| Template | Triggered by | Example context keys |
|---|---|---|
| `asset_risk` | Flood proximity, pre-field inspection | `finding_type`, `metrics.proximity_km`, `signals[]` |
| `flood_explanation` | Flood extent / depth change detection | `observation_window`, `metrics.change_percent`, `hydrology.rainfall_mm_72h` |
| `anomaly_summary` | Sensor spike / vegetation anomaly | `deviation.magnitude_std_devs`, `baseline`, `temporal_context` |

---

## 5. Database schema (key tables)

```sql
-- Core asset register
assets (
  asset_id        UUID PRIMARY KEY,
  region_code     TEXT,          -- us | uk | anz_au | anz_nz | apac
  asset_class     TEXT,          -- water_pipe | pump_station | reservoir…
  name            TEXT,
  geometry        GEOMETRY(Geometry, 4326),
  material        TEXT,
  diameter_mm     FLOAT,
  install_year    INT,
  condition_score FLOAT,         -- 0–1 (field inspection rating)
  risk_tier       TEXT,          -- low | medium | high | critical
  is_critical     BOOLEAN,
  last_inspected  DATE,
  is_active       BOOLEAN DEFAULT TRUE,
  source          TEXT           -- manual | upload:<filename> | geoserver
)

-- ML risk scores (append-only; latest via LATERAL join)
risk_scores (
  score_id        UUID PRIMARY KEY,
  asset_id        UUID REFERENCES assets,
  scored_at       TIMESTAMPTZ DEFAULT now(),
  risk_score      FLOAT,         -- 0.0–1.0
  risk_tier       TEXT,
  model_version   TEXT,
  shap_values     JSONB,         -- { feature: contribution }
  features_used   JSONB,
  anomaly_flag    BOOLEAN,
  anomaly_types   TEXT[]
)

-- TimescaleDB hypertable for sensor / SCADA observations
observations (
  time            TIMESTAMPTZ NOT NULL,
  asset_id        UUID,
  metric          TEXT,          -- pressure_psi | flow_lps | temp_c…
  value           FLOAT,
  unit            TEXT,
  quality_flag    INT,           -- 0=good, 1=uncertain, 2=bad
  source          TEXT
)

-- Pre-field inspection queue (rebuilt each pipeline run)
inspection_queue (
  queue_id        UUID PRIMARY KEY,
  asset_id        UUID REFERENCES assets,
  region_code     TEXT,
  priority_rank   INT,
  priority_score  FLOAT,
  risk_tier       TEXT,
  reason_codes    TEXT[],        -- critical_score | anomaly_detected | scheduled_review
  recommended_date DATE,
  status          TEXT DEFAULT 'pending'
)

-- Anomaly alert log
asset_alerts (
  alert_id        UUID PRIMARY KEY,
  asset_id        UUID REFERENCES assets,
  created_at      TIMESTAMPTZ DEFAULT now(),
  alert_type      TEXT,
  severity        INT,           -- 1=info … 5=critical
  message         TEXT,
  metric          TEXT,
  value           FLOAT,
  threshold       FLOAT
)

-- LLM explanation audit trail
explanation_log (
  log_id          UUID PRIMARY KEY,
  created_at      TIMESTAMPTZ DEFAULT now(),
  asset_id        UUID,
  template        TEXT,
  context         JSONB,
  explanation     TEXT,
  model           TEXT,
  latency_ms      INT
)
```

TimescaleDB automatically partitions `observations` by time, enabling efficient
range queries and retention policies without schema changes.

---

## 6. Data flow — end to end

```
                  ┌──────────────────────────────────┐
                  │        External data sources      │
                  │  EPA / USGS / OS / BOM / LINZ /   │
                  │  OpenStreetMap / CSV exports       │
                  └──────────────┬───────────────────┘
                                 │ POST /api/v1/import/upload
                                 │ (GeoPandas → WGS-84 → asyncpg)
                                 ▼
                  ┌──────────────────────────────────┐
                  │   PostgreSQL / PostGIS / TSDB     │
                  │   assets + observations tables    │
                  └──────────┬──────────┬────────────┘
                             │          │
              ┌──────────────┘          └────────────────┐
              │ GET /api/v1/geoai/run                    │ GET /api/v1/assets
              ▼                                          ▼
  ┌─────────────────────────┐              ┌─────────────────────────┐
  │  GeoAI Pipeline         │              │  FastAPI REST layer      │
  │  risk scoring           │              │  GeoJSON FeatureCollection│
  │  anomaly detection      │              └───────────┬─────────────┘
  │  SHAP attribution       │                          │ JSON
  └──────────┬──────────────┘                          ▼
             │ writes risk_scores,         ┌─────────────────────────┐
             │ inspection_queue,           │  JISP Web UI            │
             │ asset_alerts                │  MapLibre GL layers      │
             │                            │  LayerPanel tree-view    │
             │ POST /api/v1/explain        │  AssetPanel detail       │
             ▼                            └─────────────────────────┘
  ┌─────────────────────────┐
  │  Reasoning Service      │
  │  template + context     │
  │  → Ollama llama3.2      │
  │  → plain-language text  │
  └─────────────────────────┘
```

---

## 7. Frontend ↔ backend contract (known gap)

The frontend `ApiClient` expects GeoJSON FeatureCollection from `GET /api/v1/assets`:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "id": "asset-uuid",
      "geometry": { "type": "Point", "coordinates": [lon, lat] },
      "properties": {
        "id": "asset-uuid",
        "asset_code": "WP-US-001",
        "name": "Main Street Water Pipe",
        "class_code": "water_pipe",
        "class_name": "Water pipes",
        "region_code": "us",
        "region_name": "United States",
        "risk_score": 0.73,
        "risk_condition_class": "high",
        "install_year": 1987,
        "material_name": "Cast Iron"
      }
    }
  ]
}
```

The current `assets.py` route returns `{"count": N, "assets": [...]}` (flat rows,
no geometry wrapper). **This is the single blocking gap for live mode.** The route
must be rewritten to emit a proper GeoJSON FeatureCollection using
`ST_AsGeoJSON(geometry)::json` for each row.

---

## 8. Explainability contract

The reasoning layer enforces these guarantees at both the prompt-template and
Pydantic schema level:

- The response describes **what the data shows** (observed signals, measured values).
- The response does **not** predict future events or failure probability.
- The response does **not** assign a risk category or severity label.
- The response does **not** recommend actions or prioritise work.

This positions JISP explanations as decision-support context for field leads, not
as automated recommendations — preserving human judgement and compliance posture.

---

## 9. Security posture (MVP — pre-production only)

| Control | Status |
|---|---|
| CORS | `allow_origins=["*"]` — open, suitable for local PoC only |
| Authentication | None — add JWT or API-key middleware before any external exposure |
| HTTPS | Not configured — add TLS termination at Nginx for any shared deployment |
| Secrets | Stored in `.env` file — use Docker secrets or a vault in production |
| LLM isolation | Ollama runs fully local; no prompt data leaves the host |
| DB access | Single shared user (`jisp`) — add per-service roles in production |

---

## 10. MVP → production roadmap

| Phase | Scope |
|---|---|
| **Fix live mode** | Rewrite `GET /api/v1/assets` to return GeoJSON FeatureCollection |
| **Auth** | Add JWT middleware; per-user region scope |
| **GeoServer wiring** | Publish PostGIS layers as MVT; add to `map.js` as vector tile source |
| **Seed + CI** | Commit synthetic seed script; add pytest suite for API routes |
| **Real scoring model** | Replace rule model with trained XGBoost on historical inspection data |
| **WebSocket streaming** | `WS /ws/assets/{id}/stream` → real-time pressure/flow visualisation |
| **Responsive layout** | Tablet-friendly breakpoints for field tablet use |
| **Multi-tenant** | Per-organisation schemas or row-level security in PostGIS |
| **Observability** | Structured logging → ELK / Grafana; pipeline metrics dashboard |
| **Air-gap deployment** | Bundle MapLibre + fonts locally; remove all CDN dependencies |
