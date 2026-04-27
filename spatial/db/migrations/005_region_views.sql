-- JISP migration 005: per-region PostGIS views
--
-- Thin region filters over `assets` joined with reference tables and
-- the latest risk_score. These views are the surface MapLibre + the
-- API expose to the front-end and to GeoServer (each one becomes a
-- published vector-tile layer).
--
-- Views inherit the spatial index of the underlying table — no extra
-- indexes are needed here.

BEGIN;

DROP VIEW IF EXISTS jisp_us_assets   CASCADE;
DROP VIEW IF EXISTS jisp_uk_assets   CASCADE;
DROP VIEW IF EXISTS jisp_anz_assets  CASCADE;
DROP VIEW IF EXISTS jisp_apac_assets CASCADE;
DROP VIEW IF EXISTS jisp_all_assets  CASCADE;

-- ---------------------------------------------------------------
-- Base view: every asset enriched with class/material/risk metadata.
-- ---------------------------------------------------------------
CREATE VIEW jisp_all_assets AS
SELECT
    a.id,
    a.asset_code,
    a.region_code,
    r.name              AS region_name,
    a.class_code,
    ac.name             AS class_name,
    ac.domain           AS class_domain,
    ac.geometry_type    AS class_geometry_type,
    a.material_code,
    m.name              AS material_name,
    m.family            AS material_family,
    m.typical_life_yr   AS material_typical_life_yr,
    a.name,
    a.install_date,
    a.install_year,
    a.diameter_mm,
    a.length_m,
    a.attributes,
    a.source,
    a.source_id,
    a.ingested_at,
    a.updated_at,
    rs.score            AS risk_score,
    rs.condition_class  AS risk_condition_class,
    rs.computed_at      AS risk_computed_at,
    rs.model_version    AS risk_model_version,
    a.geom
FROM assets a
JOIN regions       r  ON r.region_code  = a.region_code
JOIN asset_classes ac ON ac.class_code  = a.class_code
LEFT JOIN materials m ON m.material_code = a.material_code
LEFT JOIN risk_scores rs
       ON rs.asset_id = a.id
      AND rs.is_latest = TRUE;

COMMENT ON VIEW jisp_all_assets IS
    'Base read-model view: every asset + class/material/latest-risk join. '
    'Per-region views are filters on top of this view.';


-- ---------------------------------------------------------------
-- Per-region views (one published GeoServer layer each)
-- ---------------------------------------------------------------
CREATE VIEW jisp_us_assets AS
SELECT * FROM jisp_all_assets WHERE region_code = 'us';

COMMENT ON VIEW jisp_us_assets IS
    'JISP US assets — published as GeoServer vector-tile layer jisp:us_assets.';

CREATE VIEW jisp_uk_assets AS
SELECT * FROM jisp_all_assets WHERE region_code = 'uk';

COMMENT ON VIEW jisp_uk_assets IS
    'JISP UK assets — published as GeoServer vector-tile layer jisp:uk_assets.';

CREATE VIEW jisp_anz_assets AS
SELECT * FROM jisp_all_assets WHERE region_code IN ('anz_au','anz_nz');

COMMENT ON VIEW jisp_anz_assets IS
    'JISP Australia + New Zealand assets — vector-tile layer jisp:anz_assets.';

CREATE VIEW jisp_apac_assets AS
SELECT * FROM jisp_all_assets WHERE region_code = 'apac';

COMMENT ON VIEW jisp_apac_assets IS
    'JISP APAC (non-AU/NZ) assets — vector-tile layer jisp:apac_assets.';


-- ---------------------------------------------------------------
-- High-risk subset — used directly by the inspection planner UI.
-- ---------------------------------------------------------------
DROP VIEW IF EXISTS jisp_high_risk_assets CASCADE;

CREATE VIEW jisp_high_risk_assets AS
SELECT *
FROM jisp_all_assets
WHERE risk_score IS NOT NULL
  AND risk_score >= 0.7;

COMMENT ON VIEW jisp_high_risk_assets IS
    'Assets with latest RF condition score >= 0.7. Drives MapLibre '
    'high-risk overlay + the default inspection_queue feed.';


-- ---------------------------------------------------------------
-- Latest cluster zones — published per-region for the hotspot layer.
-- ---------------------------------------------------------------
DROP VIEW IF EXISTS jisp_active_cluster_zones CASCADE;

CREATE VIEW jisp_active_cluster_zones AS
SELECT
    cz.id,
    cz.computed_at,
    cz.model_version,
    cz.region_code,
    cz.cluster_id,
    cz.num_assets,
    cz.mean_score,
    cz.persistence,
    cz.attributes,
    cz.geom
FROM cluster_zones cz
WHERE cz.is_latest = TRUE;

COMMENT ON VIEW jisp_active_cluster_zones IS
    'Most recent HDBSCAN hotspot polygons. One vector-tile layer.';

COMMIT;
