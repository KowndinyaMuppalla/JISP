BEGIN;

-- ── Assets ──────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_assets_geom     ON assets USING GIST (geometry);
CREATE INDEX IF NOT EXISTS idx_assets_region   ON assets (region_code);
CREATE INDEX IF NOT EXISTS idx_assets_class    ON assets (asset_class);
CREATE INDEX IF NOT EXISTS idx_assets_risk     ON assets (risk_tier);
CREATE INDEX IF NOT EXISTS idx_assets_name_tgm ON assets USING GIN (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_assets_attrs    ON assets USING GIN (attributes);

-- ── Observations ────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_obs_asset_time  ON observations (asset_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_obs_metric      ON observations (metric);

-- ── Alerts ──────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_alerts_asset    ON asset_alerts (asset_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_resolved ON asset_alerts (resolved) WHERE resolved = FALSE;

-- ── Risk scores ─────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_risk_asset      ON risk_scores (asset_id, scored_at DESC);
CREATE INDEX IF NOT EXISTS idx_risk_tier       ON risk_scores (risk_tier);

-- ── Cluster zones ───────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_zones_geom      ON cluster_zones USING GIST (geometry);
CREATE INDEX IF NOT EXISTS idx_zones_region    ON cluster_zones (region_code);

-- ── Inspection queue ────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_queue_rank      ON inspection_queue (priority_rank);
CREATE INDEX IF NOT EXISTS idx_queue_status    ON inspection_queue (status);

-- ── Explanation log ─────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_explog_asset    ON explanation_log (asset_id, requested_at DESC);
CREATE INDEX IF NOT EXISTS idx_explog_template ON explanation_log (template);

-- ── updated_at trigger function ─────────────────────────────────────────────
CREATE OR REPLACE FUNCTION trg_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_assets_updated_at ON assets;
CREATE TRIGGER trg_assets_updated_at
    BEFORE UPDATE ON assets
    FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

-- ── latest-row trigger for risk_scores ──────────────────────────────────────
-- Keeps a fast "is_latest" flag so reads avoid the expensive LATERAL join
-- for simple list endpoints. We add the column only if not present.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'risk_scores' AND column_name = 'is_latest'
    ) THEN
        ALTER TABLE risk_scores ADD COLUMN is_latest BOOLEAN NOT NULL DEFAULT FALSE;
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_risk_latest ON risk_scores (asset_id) WHERE is_latest = TRUE;

CREATE OR REPLACE FUNCTION trg_risk_scores_latest()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE risk_scores SET is_latest = FALSE WHERE asset_id = NEW.asset_id AND score_id <> NEW.score_id;
    NEW.is_latest = TRUE;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_risk_latest ON risk_scores;
CREATE TRIGGER trg_risk_latest
    BEFORE INSERT ON risk_scores
    FOR EACH ROW EXECUTE FUNCTION trg_risk_scores_latest();

COMMIT;
