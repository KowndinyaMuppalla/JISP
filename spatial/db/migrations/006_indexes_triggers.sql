-- JISP migration 006: secondary indexes + triggers
--
-- Most primary-path indexes were created alongside the tables they
-- accelerate (003, 004). This migration adds:
--   * Trigram + JSONB GIN indexes for free-text + attribute search.
--   * `updated_at` housekeeping triggers on every mutable table.
--   * A `risk_scores` flip-trigger that demotes the previous "latest"
--     row whenever a new one is inserted with is_latest = TRUE.
--   * A `cluster_zones` mirror of the same flip behaviour scoped to
--     (region_code, model_version) so multiple region runs coexist.

BEGIN;

-- ---------------------------------------------------------------
-- Search indexes
-- ---------------------------------------------------------------
CREATE INDEX IF NOT EXISTS assets_name_trgm_idx
    ON assets USING GIN (name gin_trgm_ops)
    WHERE name IS NOT NULL;

CREATE INDEX IF NOT EXISTS assets_attributes_gin_idx
    ON assets USING GIN (attributes jsonb_path_ops);

CREATE INDEX IF NOT EXISTS observations_attributes_gin_idx
    ON observations USING GIN (attributes jsonb_path_ops);

CREATE INDEX IF NOT EXISTS asset_alerts_attributes_gin_idx
    ON asset_alerts USING GIN (attributes jsonb_path_ops);


-- ---------------------------------------------------------------
-- updated_at trigger
-- ---------------------------------------------------------------
CREATE OR REPLACE FUNCTION jisp_set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS assets_set_updated_at ON assets;
CREATE TRIGGER assets_set_updated_at
    BEFORE UPDATE ON assets
    FOR EACH ROW
    EXECUTE FUNCTION jisp_set_updated_at();


-- ---------------------------------------------------------------
-- risk_scores: keep is_latest unique per asset
-- ---------------------------------------------------------------
-- When a new score row is inserted with is_latest=TRUE, demote any
-- previous "latest" row for that asset to FALSE. This is preferable
-- to relying on application code to do the flip and matches the
-- partial unique index defined in 004.
CREATE OR REPLACE FUNCTION jisp_risk_scores_demote_previous_latest()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.is_latest THEN
        UPDATE risk_scores
           SET is_latest = FALSE
         WHERE asset_id    = NEW.asset_id
           AND computed_at <> NEW.computed_at
           AND is_latest   = TRUE;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS risk_scores_demote_previous_latest ON risk_scores;
CREATE TRIGGER risk_scores_demote_previous_latest
    AFTER INSERT ON risk_scores
    FOR EACH ROW
    EXECUTE FUNCTION jisp_risk_scores_demote_previous_latest();


-- ---------------------------------------------------------------
-- cluster_zones: same flip pattern, scoped to (region, model_version)
-- ---------------------------------------------------------------
CREATE OR REPLACE FUNCTION jisp_cluster_zones_demote_previous_latest()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.is_latest THEN
        UPDATE cluster_zones
           SET is_latest = FALSE
         WHERE COALESCE(region_code, '')   = COALESCE(NEW.region_code, '')
           AND model_version                = NEW.model_version
           AND computed_at                <> NEW.computed_at
           AND is_latest                   = TRUE;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS cluster_zones_demote_previous_latest ON cluster_zones;
CREATE TRIGGER cluster_zones_demote_previous_latest
    AFTER INSERT ON cluster_zones
    FOR EACH ROW
    EXECUTE FUNCTION jisp_cluster_zones_demote_previous_latest();


-- ---------------------------------------------------------------
-- inspection_queue: stamp completed_at on status -> 'done'
-- ---------------------------------------------------------------
CREATE OR REPLACE FUNCTION jisp_inspection_queue_stamp_completion()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.status = 'done' AND (OLD.status IS DISTINCT FROM 'done') THEN
        NEW.completed_at := COALESCE(NEW.completed_at, now());
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS inspection_queue_stamp_completion ON inspection_queue;
CREATE TRIGGER inspection_queue_stamp_completion
    BEFORE UPDATE ON inspection_queue
    FOR EACH ROW
    EXECUTE FUNCTION jisp_inspection_queue_stamp_completion();


-- ---------------------------------------------------------------
-- asset_alerts: stamp resolved_at when resolved flips to TRUE
-- ---------------------------------------------------------------
CREATE OR REPLACE FUNCTION jisp_asset_alerts_stamp_resolved()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.resolved AND NOT COALESCE(OLD.resolved, FALSE) THEN
        NEW.resolved_at := COALESCE(NEW.resolved_at, now());
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS asset_alerts_stamp_resolved ON asset_alerts;
CREATE TRIGGER asset_alerts_stamp_resolved
    BEFORE UPDATE ON asset_alerts
    FOR EACH ROW
    EXECUTE FUNCTION jisp_asset_alerts_stamp_resolved();

COMMIT;
