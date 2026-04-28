BEGIN;

-- Per-region active asset read-models (inherit spatial indexes from assets table)
CREATE OR REPLACE VIEW v_assets_us   AS SELECT * FROM assets WHERE region_code = 'US'   AND is_active = TRUE;
CREATE OR REPLACE VIEW v_assets_uk   AS SELECT * FROM assets WHERE region_code = 'UK'   AND is_active = TRUE;
CREATE OR REPLACE VIEW v_assets_anz  AS SELECT * FROM assets WHERE region_code = 'ANZ'  AND is_active = TRUE;
CREATE OR REPLACE VIEW v_assets_apac AS SELECT * FROM assets WHERE region_code = 'APAC' AND is_active = TRUE;

-- Assets joined with their latest risk score
CREATE OR REPLACE VIEW v_assets_with_risk AS
SELECT
    a.*,
    rs.risk_score,
    rs.risk_tier     AS ai_risk_tier,
    rs.anomaly_flag,
    rs.scored_at
FROM assets a
LEFT JOIN LATERAL (
    SELECT risk_score, risk_tier, anomaly_flag, scored_at
    FROM risk_scores
    WHERE asset_id = a.asset_id
    ORDER BY scored_at DESC
    LIMIT 1
) rs ON TRUE
WHERE a.is_active = TRUE;

-- High-risk assets requiring attention
CREATE OR REPLACE VIEW v_high_risk_assets AS
SELECT a.*, rs.risk_score, rs.scored_at
FROM assets a
JOIN LATERAL (
    SELECT risk_score, scored_at
    FROM risk_scores
    WHERE asset_id = a.asset_id
    ORDER BY scored_at DESC
    LIMIT 1
) rs ON rs.risk_score >= 55
WHERE a.is_active = TRUE
ORDER BY rs.risk_score DESC;

-- Pending inspection queue with full asset details
CREATE OR REPLACE VIEW v_inspection_queue_full AS
SELECT
    iq.*,
    a.name,
    a.asset_class,
    a.geometry,
    a.region_code,
    a.condition_score,
    a.last_inspected,
    a.material,
    a.install_year
FROM inspection_queue iq
JOIN assets a ON a.asset_id = iq.asset_id
WHERE iq.status = 'pending'
ORDER BY iq.priority_rank;

COMMIT;
