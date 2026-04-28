-- JISP migration 004: time-series + GeoAI result tables
--
-- Aligned with feat/jisp-mvp:spatial/db/schema.sql.
-- Six tables created here:
--   observations      — TimescaleDB hypertable of raw sensor readings
--   asset_alerts      — anomaly + threshold-breach events (severity 1-5)
--   risk_scores       — per-asset RF condition score (0-100)
--   cluster_zones     — spatial hotspot polygons
--   inspection_queue  — ranked inspection backlog from the planner
--   explanation_log   — audit log of /explain calls

BEGIN;

-- ---------------------------------------------------------------
-- observations  (TimescaleDB hypertable)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS observations (
    time          TIMESTAMPTZ      NOT NULL,
    asset_id      UUID             NOT NULL
        REFERENCES assets(asset_id) ON DELETE CASCADE,
    metric        TEXT             NOT NULL,
    value         DOUBLE PRECISION NOT NULL,
    unit          TEXT,
    quality_flag  SMALLINT         NOT NULL DEFAULT 0
                      CHECK (quality_flag IN (0, 1, 2)),
    source        TEXT             NOT NULL DEFAULT 'sensor'
);

COMMENT ON TABLE observations IS
    'Time-series readings for assets. Hypertable partitioned on `time`. '
    'A single asset may report multiple metrics (flow, pressure, turbidity).';

SELECT create_hypertable(
    'observations',
    'time',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists       => TRUE
);

CREATE INDEX IF NOT EXISTS idx_obs_asset_time
    ON observations (asset_id, time DESC);


-- ---------------------------------------------------------------
-- asset_alerts
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS asset_alerts (
    alert_id     UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    asset_id     UUID NOT NULL
        REFERENCES assets(asset_id) ON DELETE CASCADE,
    time         TIMESTAMPTZ NOT NULL DEFAULT now(),
    alert_type   TEXT NOT NULL,
    severity     INTEGER NOT NULL CHECK (severity BETWEEN 1 AND 5),
    message      TEXT NOT NULL,
    metric       TEXT,
    value        DOUBLE PRECISION,
    threshold    DOUBLE PRECISION,
    resolved     BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_at  TIMESTAMPTZ
);

COMMENT ON TABLE asset_alerts IS
    'Anomaly / threshold-breach events emitted by the GeoAI pipeline. '
    'Severity is a 1-5 integer (1 = info, 5 = critical).';

CREATE INDEX IF NOT EXISTS idx_alerts_asset
    ON asset_alerts (asset_id, time DESC);

CREATE INDEX IF NOT EXISTS idx_alerts_unresolved
    ON asset_alerts (severity DESC, time DESC) WHERE resolved = FALSE;


-- ---------------------------------------------------------------
-- risk_scores
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS risk_scores (
    score_id        UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    asset_id        UUID NOT NULL
        REFERENCES assets(asset_id) ON DELETE CASCADE,
    scored_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    risk_score      DOUBLE PRECISION NOT NULL
                        CHECK (risk_score BETWEEN 0 AND 100),
    risk_tier       TEXT NOT NULL
                        CHECK (risk_tier IN ('critical', 'high', 'medium', 'low')),
    model_version   TEXT NOT NULL DEFAULT 'v1',
    shap_values     JSONB,
    features_used   JSONB,
    anomaly_flag    BOOLEAN NOT NULL DEFAULT FALSE,
    anomaly_types   TEXT[],
    notes           TEXT
);

COMMENT ON TABLE risk_scores IS
    'Per-asset condition risk score from the GeoAI RF model (0-100). '
    'History is preserved; latest row is found by ORDER BY scored_at DESC.';

CREATE INDEX IF NOT EXISTS idx_risk_asset
    ON risk_scores (asset_id, scored_at DESC);


-- ---------------------------------------------------------------
-- cluster_zones
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cluster_zones (
    zone_id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    region_code     TEXT REFERENCES regions(code) ON UPDATE CASCADE,
    geometry        GEOMETRY(Polygon, 4326) NOT NULL,
    cluster_id      INTEGER NOT NULL,
    asset_count     INTEGER,
    avg_risk        DOUBLE PRECISION,
    dominant_class  TEXT,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE cluster_zones IS
    'Spatial hotspot polygons over high-risk assets (HDBSCAN-derived).';

CREATE INDEX IF NOT EXISTS idx_zones_geom
    ON cluster_zones USING GIST (geometry);

CREATE INDEX IF NOT EXISTS idx_zones_region_time
    ON cluster_zones (region_code, computed_at DESC);


-- ---------------------------------------------------------------
-- inspection_queue
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS inspection_queue (
    queue_id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    asset_id          UUID NOT NULL
        REFERENCES assets(asset_id) ON DELETE CASCADE,
    region_code       TEXT REFERENCES regions(code) ON UPDATE CASCADE,
    priority_rank     INTEGER NOT NULL,
    priority_score    DOUBLE PRECISION NOT NULL,
    risk_tier         TEXT,
    reason_codes      TEXT[],
    recommended_date  DATE,
    generated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    status            TEXT NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending','scheduled','completed','cancelled'))
);

COMMENT ON TABLE inspection_queue IS
    'Ranked field-inspection backlog. Populated by the GeoAI planner '
    'from risk_scores + asset_alerts. priority_rank is dense (1..N).';

CREATE INDEX IF NOT EXISTS idx_queue_rank
    ON inspection_queue (priority_rank);

CREATE INDEX IF NOT EXISTS idx_queue_open
    ON inspection_queue (priority_rank ASC)
    WHERE status IN ('pending','scheduled');


-- ---------------------------------------------------------------
-- explanation_log
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS explanation_log (
    log_id        UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    asset_id      UUID REFERENCES assets(asset_id) ON DELETE SET NULL,
    requested_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    template      TEXT NOT NULL,
    context       JSONB,
    explanation   TEXT NOT NULL,
    model         TEXT NOT NULL DEFAULT 'llama3.2',
    latency_ms    INTEGER CHECK (latency_ms IS NULL OR latency_ms >= 0)
);

COMMENT ON TABLE explanation_log IS
    'Audit + reuse log of every /explain call. Stores prompt context, '
    'response, model, and latency for traceability.';

CREATE INDEX IF NOT EXISTS idx_explain_asset_time
    ON explanation_log (asset_id, requested_at DESC);

CREATE INDEX IF NOT EXISTS idx_explain_template_time
    ON explanation_log (template, requested_at DESC);

COMMIT;
