-- JISP migration 002: reference / lookup tables
--
-- Aligned with the mvp canonical schema (feat/jisp-mvp:spatial/db/schema.sql).
-- Two reference tables drive routing, units, and asset taxonomy:
--
--   regions        — operational regions (US, UK, ANZ, APAC) plus the
--                    region-specific working SRID + unit system + the
--                    regulatory body whose definitions the platform
--                    follows when it produces inspection reports.
--   asset_classes  — short, code-driven taxonomy of asset types
--                    (water, wastewater, stormwater, flood).
--
-- Materials are tracked as a free-text `material` column on `assets`
-- in the mvp shape (no separate dictionary table).

BEGIN;

-- ---------------------------------------------------------------
-- regions
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS regions (
    code             TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    srid             INT  NOT NULL DEFAULT 4326,
    unit_system      TEXT NOT NULL DEFAULT 'metric',
    regulatory_body  TEXT,
    country_codes    TEXT[]
);

COMMENT ON TABLE regions IS
    'JISP operational regions. Drives per-region views (migration 005) and '
    'unit/SRID selection at the API layer.';

INSERT INTO regions (code, name, srid, unit_system, regulatory_body, country_codes) VALUES
    ('US',   'United States',          4269, 'imperial', 'EPA/AWWA',     ARRAY['US']),
    ('UK',   'United Kingdom',        27700, 'metric',   'EA/Ofwat',     ARRAY['GB']),
    ('ANZ',  'Australia & NZ',         4283, 'metric',   'WSAA/MfE',     ARRAY['AU','NZ']),
    ('APAC', 'Asia Pacific',           4326, 'metric',   'ISO 24510',    ARRAY['SG','JP','IN','HK'])
ON CONFLICT (code) DO NOTHING;


-- ---------------------------------------------------------------
-- asset_classes
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS asset_classes (
    code           TEXT PRIMARY KEY,
    label          TEXT NOT NULL,
    geometry_type  TEXT NOT NULL,
    domain         TEXT NOT NULL DEFAULT 'water'
);

COMMENT ON TABLE asset_classes IS
    'Asset taxonomy. Codes are short and uppercase to keep the assets '
    'table compact; the `label` column is the human-readable form.';

INSERT INTO asset_classes (code, label, geometry_type, domain) VALUES
    ('WTP',       'Water Treatment Plant',     'Point',      'water'),
    ('WWTP',      'Wastewater Treatment Plant','Point',      'wastewater'),
    ('PUMP',      'Pump Station',              'Point',      'water'),
    ('RESERVOIR', 'Reservoir',                 'Polygon',    'water'),
    ('DAM',       'Dam',                       'Point',      'water'),
    ('PIPE_W',    'Water Main',                'LineString', 'water'),
    ('PIPE_S',    'Sewer Main',                'LineString', 'wastewater'),
    ('PIPE_ST',   'Stormwater Drain',          'LineString', 'stormwater'),
    ('VALVE',     'Valve',                     'Point',      'water'),
    ('HYDRANT',   'Fire Hydrant',              'Point',      'water'),
    ('METER',     'Water Meter',               'Point',      'water'),
    ('MANHOLE',   'Manhole',                   'Point',      'wastewater'),
    ('SENSOR',    'Monitoring Sensor',         'Point',      'water'),
    ('FLOOD_Z',   'Flood Risk Zone',           'Polygon',    'flood'),
    ('CATCHMENT', 'Drainage Catchment',        'Polygon',    'stormwater')
ON CONFLICT (code) DO NOTHING;

COMMIT;
