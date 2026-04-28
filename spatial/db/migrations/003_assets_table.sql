BEGIN;

CREATE TABLE IF NOT EXISTS assets (
    asset_id        UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    external_id     TEXT,
    region_code     TEXT NOT NULL REFERENCES regions(code),
    asset_class     TEXT NOT NULL REFERENCES asset_classes(code),
    name            TEXT NOT NULL,
    description     TEXT,
    owner           TEXT,
    geometry        GEOMETRY(Geometry, 4326) NOT NULL,
    material        TEXT,
    diameter_mm     FLOAT,
    length_m        FLOAT,
    capacity_ml     FLOAT,
    elevation_m     FLOAT,
    depth_m         FLOAT,
    pressure_zone   TEXT,
    install_year    INT,
    condition_score FLOAT CHECK (condition_score BETWEEN 0 AND 100),
    risk_tier       TEXT CHECK (risk_tier IN ('critical','high','medium','low','unknown')) DEFAULT 'unknown',
    last_inspected  DATE,
    next_inspection DATE,
    is_critical     BOOLEAN NOT NULL DEFAULT FALSE,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    attributes      JSONB   NOT NULL DEFAULT '{}',
    source          TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_asset_geometry_type CHECK (
        GeometryType(geometry) IN (
            'POINT','LINESTRING','POLYGON',
            'MULTIPOINT','MULTILINESTRING','MULTIPOLYGON',
            'GEOMETRYCOLLECTION'
        )
    )
);

COMMIT;
