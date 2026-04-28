-- JISP migration 005: per-region + risk-enriched views
--
-- Aligned with feat/jisp-mvp:spatial/db/schema.sql.
-- Six views: one per operational region (US, UK, ANZ, APAC), one
-- joining the latest risk_score per asset, and one expanding the
-- inspection_queue with the joined asset record.
--
-- Views inherit the spatial index of the underlying table — no extra
-- indexes are needed here.

BEGIN;

DROP VIEW IF EXISTS v_inspection_queue_full CASCADE;
DROP VIEW IF EXISTS v_assets_with_risk      CASCADE;
DROP VIEW IF EXISTS v_assets_apac           CASCADE;
DROP VIEW IF EXISTS v_assets_anz            CASCADE;
DROP VIEW IF EXISTS v_assets_uk             CASCADE;
DROP VIEW IF EXISTS v_assets_us             CASCADE;

-- ---------------------------------------------------------------
-- Per-region active-asset views
-- ---------------------------------------------------------------
CREATE OR REPLACE VIEW v_assets_us AS
    SELECT * FROM assets WHERE region_code = 'US' AND is_active = TRUE;

CREATE OR REPLACE VIEW v_assets_uk AS
    SELECT * FROM assets WHERE region_code = 'UK' AND is_active = TRUE;

CREATE OR REPLACE VIEW v_assets_anz AS
    SELECT * FROM assets WHERE region_code = 'ANZ' AND is_active = TRUE;

CREATE OR REPLACE VIEW v_assets_apac AS
    SELECT * FROM assets WHERE region_code = 'APAC' AND is_active = TRUE;

COMMENT ON VIEW v_assets_us   IS 'Active US assets — published as a GeoServer vector-tile layer.';
COMMENT ON VIEW v_assets_uk   IS 'Active UK assets — published as a GeoServer vector-tile layer.';
COMMENT ON VIEW v_assets_anz  IS 'Active Australia + New Zealand assets — vector-tile layer.';
COMMENT ON VIEW v_assets_apac IS 'Active APAC (non-AU/NZ) assets — vector-tile layer.';


-- ---------------------------------------------------------------
-- Latest-risk join — every active asset enriched with the most recent
-- risk_score row (NULLs where no score has been computed yet).
-- ---------------------------------------------------------------
CREATE OR REPLACE VIEW v_assets_with_risk AS
SELECT
    a.*,
    rs.risk_score,
    rs.risk_tier      AS ai_risk_tier,
    rs.anomaly_flag,
    rs.scored_at
FROM assets a
LEFT JOIN LATERAL (
    SELECT risk_score, risk_tier, anomaly_flag, scored_at
    FROM   risk_scores
    WHERE  asset_id = a.asset_id
    ORDER  BY scored_at DESC
    LIMIT  1
) rs ON TRUE
WHERE a.is_active = TRUE;

COMMENT ON VIEW v_assets_with_risk IS
    'Active assets joined with their most recent risk_scores row. The '
    'GeoAI map overlay reads from this view.';


-- ---------------------------------------------------------------
-- Inspection queue — joined with the asset record so the planner UI
-- has everything it needs in one fetch.
-- ---------------------------------------------------------------
CREATE OR REPLACE VIEW v_inspection_queue_full AS
SELECT
    iq.*,
    a.name,
    a.asset_class,
    a.geometry,
    a.region_code     AS asset_region_code,
    a.condition_score,
    a.last_inspected,
    a.material,
    a.install_year
FROM inspection_queue iq
JOIN assets a ON a.asset_id = iq.asset_id
WHERE iq.status = 'pending'
ORDER BY iq.priority_rank;

COMMENT ON VIEW v_inspection_queue_full IS
    'Open inspection queue rows joined with the underlying asset record. '
    'Drives the inspection-planner UI in the front-end.';

COMMIT;
