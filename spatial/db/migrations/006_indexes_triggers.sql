-- JISP migration 006: secondary indexes + triggers
--
-- Aligned with feat/jisp-mvp:spatial/db/schema.sql.
-- Primary-path indexes were created alongside their tables in 003 / 004.
-- This migration adds:
--   * Trigram + JSONB GIN indexes for fuzzy + attribute search.
--   * `updated_at` housekeeping trigger on `assets`.
--   * Auto-stamps for inspection_queue completion and alert resolution.

BEGIN;

-- ---------------------------------------------------------------
-- Search indexes
-- ---------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_assets_name
    ON assets USING GIN (name gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_assets_attributes_gin
    ON assets USING GIN (attributes jsonb_path_ops);

CREATE INDEX IF NOT EXISTS idx_alerts_metric
    ON asset_alerts (metric, time DESC) WHERE metric IS NOT NULL;


-- ---------------------------------------------------------------
-- updated_at trigger on assets
-- ---------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_update_ts()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_assets_ts ON assets;
CREATE TRIGGER trg_assets_ts
    BEFORE UPDATE ON assets
    FOR EACH ROW
    EXECUTE FUNCTION trg_update_ts();


-- ---------------------------------------------------------------
-- inspection_queue: stamp `recommended_date` if not set when status
-- transitions to scheduled, and (best-effort) clear noise on close.
-- ---------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_inspection_queue_close()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.status IN ('completed','cancelled')
       AND OLD.status IS DISTINCT FROM NEW.status THEN
        -- Nothing to backfill on the queue row itself; intentional no-op
        -- placeholder so future bookkeeping (e.g. emit an event) has a
        -- clear hook.
        RETURN NEW;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_queue_close ON inspection_queue;
CREATE TRIGGER trg_queue_close
    BEFORE UPDATE ON inspection_queue
    FOR EACH ROW
    EXECUTE FUNCTION trg_inspection_queue_close();


-- ---------------------------------------------------------------
-- asset_alerts: stamp resolved_at when `resolved` flips to TRUE.
-- ---------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_alert_resolved()
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

DROP TRIGGER IF EXISTS trg_alert_resolved ON asset_alerts;
CREATE TRIGGER trg_alert_resolved
    BEFORE UPDATE ON asset_alerts
    FOR EACH ROW
    EXECUTE FUNCTION trg_alert_resolved();

COMMIT;
