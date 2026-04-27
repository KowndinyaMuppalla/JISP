-- JISP migration 004: time-series + GeoAI result tables
--
-- Five tables created here:
--   observations        — TimescaleDB hypertable, raw sensor / SCADA / WQ readings
--   asset_alerts        — anomaly + threshold-breach events
--   risk_scores         — per-asset condition score from the GeoAI RF model
--   cluster_zones       — HDBSCAN spatial hotspot polygons
--   inspection_queue    — ranked inspection backlog produced by the planner
--   explanation_log     — record of /explain calls for audit + reuse
--
-- Hypertable note: TimescaleDB's create_hypertable() does not support
-- `IF NOT EXISTS` natively as a flag in older 2.x — the `if_not_exists`
-- parameter is used here, which is supported in 2.0+.

BEGIN;

-- ---------------------------------------------------------------
-- observations  (TimescaleDB hypertable)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS observations (
    time          TIMESTAMPTZ NOT NULL,
    asset_id      UUID        NOT NULL
        REFERENCES assets(id) ON DELETE CASCADE,
    metric        TEXT        NOT NULL,
    value         DOUBLE PRECISION,
    unit          TEXT,
    source        TEXT NOT NULL DEFAULT 'unknown',
    attributes    JSONB NOT NULL DEFAULT '{}'::jsonb,
    geom          GEOMETRY(Point, 4326),
    ingested_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT observations_metric_chk
        CHECK (metric <> ''),

    CONSTRAINT observations_value_finite_chk
        CHECK (value IS NULL OR (value = value AND value <> 'Infinity'::float8 AND value <> '-Infinity'::float8))
);

COMMENT ON TABLE observations IS
    'Time-series readings for assets. Hypertable partitioned on `time`. '
    'A single asset may report multiple metrics (flow, pressure, turbidity).';

-- Convert into a TimescaleDB hypertable. 7-day chunks balance ingest
-- throughput against query plan size for the typical 90-day rolling
-- analyses run by the GeoAI anomaly model.
SELECT create_hypertable(
    'observations',
    'time',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists       => TRUE
);

CREATE INDEX IF NOT EXISTS observations_asset_metric_time_idx
    ON observations (asset_id, metric, time DESC);

CREATE INDEX IF NOT EXISTS observations_metric_time_idx
    ON observations (metric, time DESC);

CREATE INDEX IF NOT EXISTS observations_geom_gix
    ON observations USING GIST (geom);


-- ---------------------------------------------------------------
-- asset_alerts
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS asset_alerts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id        UUID NOT NULL
        REFERENCES assets(id) ON DELETE CASCADE,
    time            TIMESTAMPTZ NOT NULL DEFAULT now(),
    severity        TEXT NOT NULL
        CHECK (severity IN ('info','low','medium','high','critical')),
    alert_type      TEXT NOT NULL,
    message         TEXT NOT NULL,
    metric          TEXT,
    observed_value  DOUBLE PRECISION,
    threshold       DOUBLE PRECISION,
    attributes      JSONB NOT NULL DEFAULT '{}'::jsonb,
    resolved        BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE asset_alerts IS
    'Anomaly / threshold-breach events emitted by GeoAI or rule engines.';

CREATE INDEX IF NOT EXISTS asset_alerts_asset_time_idx
    ON asset_alerts (asset_id, time DESC);

CREATE INDEX IF NOT EXISTS asset_alerts_unresolved_idx
    ON asset_alerts (severity, time DESC) WHERE resolved = FALSE;


-- ---------------------------------------------------------------
-- risk_scores
-- ---------------------------------------------------------------
-- The Random Forest condition model writes one row per asset per
-- model run. Composite primary key keeps history; a partial unique
-- index on (asset_id) WHERE is_latest captures the active score.
CREATE TABLE IF NOT EXISTS risk_scores (
    asset_id        UUID NOT NULL
        REFERENCES assets(id) ON DELETE CASCADE,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    model_version   TEXT NOT NULL,
    score           DOUBLE PRECISION NOT NULL
        CHECK (score >= 0.0 AND score <= 1.0),
    condition_class TEXT NOT NULL
        CHECK (condition_class IN ('excellent','good','fair','poor','critical')),
    feature_values  JSONB NOT NULL DEFAULT '{}'::jsonb,
    shap_values     JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_latest       BOOLEAN NOT NULL DEFAULT TRUE,

    PRIMARY KEY (asset_id, computed_at)
);

COMMENT ON TABLE risk_scores IS
    'Per-asset condition risk score from the GeoAI RF model. '
    'Keeps history; only one row per asset has is_latest=TRUE.';

CREATE UNIQUE INDEX IF NOT EXISTS risk_scores_latest_uq
    ON risk_scores (asset_id) WHERE is_latest = TRUE;

CREATE INDEX IF NOT EXISTS risk_scores_score_idx
    ON risk_scores (score DESC) WHERE is_latest = TRUE;


-- ---------------------------------------------------------------
-- cluster_zones
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cluster_zones (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    model_version   TEXT NOT NULL,
    region_code     TEXT
        REFERENCES regions(region_code) ON UPDATE CASCADE,
    cluster_id      INTEGER NOT NULL,
    geom            GEOMETRY(Polygon, 4326) NOT NULL,
    num_assets      INTEGER NOT NULL CHECK (num_assets >= 0),
    mean_score      DOUBLE PRECISION
        CHECK (mean_score IS NULL OR (mean_score >= 0.0 AND mean_score <= 1.0)),
    persistence     DOUBLE PRECISION,
    attributes      JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_latest       BOOLEAN NOT NULL DEFAULT TRUE
);

COMMENT ON TABLE cluster_zones IS
    'HDBSCAN-derived spatial hotspot polygons over high-risk assets.';

CREATE INDEX IF NOT EXISTS cluster_zones_geom_gix
    ON cluster_zones USING GIST (geom);

CREATE INDEX IF NOT EXISTS cluster_zones_region_latest_idx
    ON cluster_zones (region_code, computed_at DESC) WHERE is_latest = TRUE;


-- ---------------------------------------------------------------
-- inspection_queue
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS inspection_queue (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id        UUID NOT NULL
        REFERENCES assets(id) ON DELETE CASCADE,
    queued_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    priority        INTEGER NOT NULL CHECK (priority BETWEEN 1 AND 5),
    reason          TEXT NOT NULL,
    risk_score      DOUBLE PRECISION
        CHECK (risk_score IS NULL OR (risk_score >= 0.0 AND risk_score <= 1.0)),
    status          TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','scheduled','in_progress','done','cancelled')),
    scheduled_for   TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    attributes      JSONB NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE inspection_queue IS
    'Ranked field-inspection backlog. Populated by the GeoAI planner '
    'from risk_scores + cluster_zones.';

CREATE INDEX IF NOT EXISTS inspection_queue_asset_idx
    ON inspection_queue (asset_id);

CREATE INDEX IF NOT EXISTS inspection_queue_open_idx
    ON inspection_queue (priority ASC, queued_at ASC)
    WHERE status IN ('pending','scheduled');


-- ---------------------------------------------------------------
-- explanation_log
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS explanation_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id        UUID
        REFERENCES assets(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finding_type    TEXT NOT NULL,
    prompt_text     TEXT NOT NULL,
    llm_model       TEXT NOT NULL,
    response_text   TEXT NOT NULL,
    latency_ms      INTEGER CHECK (latency_ms IS NULL OR latency_ms >= 0),
    tokens_in       INTEGER,
    tokens_out      INTEGER,
    attributes      JSONB NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE explanation_log IS
    'Audit + reuse log of every /explain call. Stores prompt, response, '
    'model, and latency for traceability.';

CREATE INDEX IF NOT EXISTS explanation_log_asset_time_idx
    ON explanation_log (asset_id, created_at DESC);

CREATE INDEX IF NOT EXISTS explanation_log_finding_idx
    ON explanation_log (finding_type, created_at DESC);

COMMIT;
