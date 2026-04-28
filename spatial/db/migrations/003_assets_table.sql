-- JISP migration 003: unified assets table
--
-- Aligned with feat/jisp-mvp:spatial/db/schema.sql.
-- A single `assets` table holds every region and every class so that
-- spatial queries are region-agnostic and the GeoAI pipeline can train
-- across regions with no joins. Geometry is always stored in EPSG:4326;
-- per-region working SRID is recorded in `regions.srid` (migration 002).

BEGIN;

CREATE TABLE IF NOT EXISTS assets (
    asset_id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Source / external system identifier (free-form; not unique).
    external_id       TEXT,

    region_code       TEXT NOT NULL REFERENCES regions(code)
                          ON UPDATE CASCADE,
    asset_class       TEXT NOT NULL REFERENCES asset_classes(code)
                          ON UPDATE CASCADE,

    name              TEXT NOT NULL,
    description       TEXT,
    owner             TEXT,

    geometry          GEOMETRY(Geometry, 4326) NOT NULL,

    -- Physical attributes (nullable; populated from source where available)
    material          TEXT,
    diameter_mm       DOUBLE PRECISION,
    length_m          DOUBLE PRECISION,
    capacity_ml       DOUBLE PRECISION,
    elevation_m       DOUBLE PRECISION,
    depth_m           DOUBLE PRECISION,
    pressure_zone     TEXT,
    install_year      INTEGER,

    -- Condition & risk (mvp scoring is on a 0-100 scale, not 0-1)
    condition_score   DOUBLE PRECISION
                          CHECK (condition_score IS NULL OR
                                 (condition_score BETWEEN 0 AND 100)),
    risk_tier         TEXT NOT NULL DEFAULT 'unknown'
                          CHECK (risk_tier IN ('critical','high','medium','low','unknown')),

    -- Inspection lifecycle
    last_inspected    DATE,
    next_inspection   DATE,
    is_critical       BOOLEAN NOT NULL DEFAULT FALSE,
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,

    -- Free-form source attributes preserved verbatim from ingestion.
    attributes        JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Provenance
    source            TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT assets_install_year_chk
        CHECK (install_year IS NULL OR install_year BETWEEN 1700 AND 2100),
    CONSTRAINT assets_diameter_chk
        CHECK (diameter_mm IS NULL OR diameter_mm > 0),
    CONSTRAINT assets_length_chk
        CHECK (length_m IS NULL OR length_m > 0)
);

-- Spatial index — required for any ST_* query at scale.
CREATE INDEX IF NOT EXISTS idx_assets_geom    ON assets USING GIST (geometry);
CREATE INDEX IF NOT EXISTS idx_assets_region  ON assets (region_code);
CREATE INDEX IF NOT EXISTS idx_assets_class   ON assets (asset_class);
CREATE INDEX IF NOT EXISTS idx_assets_risk    ON assets (risk_tier);

-- External-id lookup (one external_id may legitimately repeat across
-- sources, so this is a regular index, not unique).
CREATE INDEX IF NOT EXISTS idx_assets_external_id
    ON assets (external_id) WHERE external_id IS NOT NULL;

COMMENT ON TABLE assets IS
    'Unified multi-region, multi-class asset register. WGS84 geometry. '
    'GeoAI pipeline + per-region views (005) read directly from this table.';

COMMIT;
