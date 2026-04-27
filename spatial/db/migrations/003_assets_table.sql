-- JISP migration 003: unified assets table
--
-- All asset classes across all regions live in a single `assets` table
-- so that:
--   * spatial queries can be region-agnostic (SELECT * FROM assets WHERE
--     ST_Intersects(geom, :bbox)),
--   * per-region views (migration 005) are thin filters,
--   * the GeoAI pipeline trains on cross-region data without joins.
--
-- Geometry is always stored in EPSG:4326 (WGS84). Source-CRS conversion
-- happens at the ingestion layer.
--
-- The geometry column is generic GEOMETRY rather than a typed
-- (Point|LineString|Polygon) so a single table can host every asset
-- class. Per-class geometry-type integrity is enforced by a CHECK
-- constraint that compares the asset's class to the geometry's GeometryType().

BEGIN;

CREATE TABLE IF NOT EXISTS assets (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),

    -- External / source identifier (e.g. EPA FRS ID, OS TOID, BOM gauge).
    -- Combined with `source` it must be unique so re-ingestion upserts
    -- cleanly; a NULL asset_code is allowed for purely internally-created
    -- assets (e.g. uploaded shapefiles without a stable ID column).
    asset_code      TEXT,

    region_code     TEXT NOT NULL
        REFERENCES regions(region_code) ON UPDATE CASCADE,
    class_code      TEXT NOT NULL
        REFERENCES asset_classes(class_code) ON UPDATE CASCADE,
    material_code   TEXT
        REFERENCES materials(material_code) ON UPDATE CASCADE,

    name            TEXT,
    geom            GEOMETRY(Geometry, 4326) NOT NULL,

    install_date    DATE,
    install_year    INTEGER,
    diameter_mm     DOUBLE PRECISION,
    length_m        DOUBLE PRECISION,

    -- Free-form source attributes preserved verbatim from ingestion.
    -- Promoted to first-class columns only when the GeoAI pipeline
    -- needs to model them.
    attributes      JSONB        NOT NULL DEFAULT '{}'::jsonb,

    -- Provenance: where this row came from. `source` is a slug
    -- (e.g. 'epa_frs', 'os_water_network', 'upload:gpkg'); `source_id`
    -- is the source-side primary key.
    source          TEXT NOT NULL DEFAULT 'unknown',
    source_id       TEXT,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT assets_install_year_chk
        CHECK (install_year IS NULL OR install_year BETWEEN 1700 AND 2100),

    CONSTRAINT assets_diameter_chk
        CHECK (diameter_mm IS NULL OR diameter_mm > 0),

    CONSTRAINT assets_length_chk
        CHECK (length_m IS NULL OR length_m > 0),

    -- Enforce geometry type matches the asset class declaration.
    -- (multilinestring / multipolygon assets are also accepted for
    -- linestring / polygon classes respectively to keep ingestion
    -- forgiving.)
    CONSTRAINT assets_geom_type_chk CHECK (
        (
            (SELECT geometry_type FROM asset_classes ac WHERE ac.class_code = assets.class_code)
            IS NULL
        )
        OR
        (
            (
                (SELECT geometry_type FROM asset_classes ac WHERE ac.class_code = assets.class_code) = 'point'
                AND GeometryType(geom) IN ('POINT','MULTIPOINT')
            )
            OR
            (
                (SELECT geometry_type FROM asset_classes ac WHERE ac.class_code = assets.class_code) = 'linestring'
                AND GeometryType(geom) IN ('LINESTRING','MULTILINESTRING')
            )
            OR
            (
                (SELECT geometry_type FROM asset_classes ac WHERE ac.class_code = assets.class_code) = 'multilinestring'
                AND GeometryType(geom) IN ('LINESTRING','MULTILINESTRING')
            )
            OR
            (
                (SELECT geometry_type FROM asset_classes ac WHERE ac.class_code = assets.class_code) = 'polygon'
                AND GeometryType(geom) IN ('POLYGON','MULTIPOLYGON')
            )
            OR
            (
                (SELECT geometry_type FROM asset_classes ac WHERE ac.class_code = assets.class_code) = 'multipolygon'
                AND GeometryType(geom) IN ('POLYGON','MULTIPOLYGON')
            )
        )
    )
);

-- Source uniqueness: same source must not produce duplicate rows.
CREATE UNIQUE INDEX IF NOT EXISTS assets_source_natural_key_idx
    ON assets (source, source_id)
    WHERE source_id IS NOT NULL;

-- Asset-code lookups are common from the API; allow non-unique because
-- two regions could conceivably share an asset_code.
CREATE INDEX IF NOT EXISTS assets_asset_code_idx
    ON assets (asset_code)
    WHERE asset_code IS NOT NULL;

CREATE INDEX IF NOT EXISTS assets_region_class_idx
    ON assets (region_code, class_code);

-- Spatial index — required for any ST_* query at scale.
CREATE INDEX IF NOT EXISTS assets_geom_gix
    ON assets USING GIST (geom);

COMMENT ON TABLE assets IS
    'Unified multi-region, multi-class asset register. WGS84 geometry. '
    'GeoAI pipeline + per-region views read directly from this table.';

COMMIT;
