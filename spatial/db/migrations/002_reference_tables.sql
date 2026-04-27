-- JISP migration 002: reference / lookup tables
--
-- Three small reference tables keep the unified `assets` table (003)
-- compact and portable across regions:
--
--   regions         — JISP operational regions (US, UK, ANZ-AU, ANZ-NZ, APAC)
--   asset_classes   — domain-specific asset taxonomy (Jacobs Water focus)
--   materials       — pipe / structure construction materials
--
-- Inserts are idempotent (ON CONFLICT DO NOTHING) so seeding is safe
-- to re-run.

BEGIN;

-- ---------------------------------------------------------------
-- regions
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS regions (
    region_code   TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    iso_a2        TEXT,
    timezone      TEXT NOT NULL DEFAULT 'UTC',
    bbox          GEOMETRY(Polygon, 4326),
    description   TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE regions IS
    'JISP operational regions. Drives per-region views and ingestion routing.';

INSERT INTO regions (region_code, name, iso_a2, timezone, bbox, description) VALUES
    ('us',     'United States',           'US', 'America/New_York',
        ST_SetSRID(ST_MakeEnvelope(-125.0,  24.0,  -66.0,  49.5), 4326),
        'Continental US — EPA FRS, USGS NWIS, FEMA flood layers.'),
    ('uk',     'United Kingdom',          'GB', 'Europe/London',
        ST_SetSRID(ST_MakeEnvelope(  -8.7,  49.8,    1.8,  60.9), 4326),
        'United Kingdom — Environment Agency, OS OpenData, OS Water Network.'),
    ('anz_au', 'Australia',               'AU', 'Australia/Sydney',
        ST_SetSRID(ST_MakeEnvelope( 112.0, -44.0,  154.0,  -9.0), 4326),
        'Australia — Bureau of Meteorology catchments, Geoscience Australia.'),
    ('anz_nz', 'New Zealand',             'NZ', 'Pacific/Auckland',
        ST_SetSRID(ST_MakeEnvelope( 165.5, -47.5,  179.0, -33.5), 4326),
        'New Zealand — LINZ topographic + hydro layers.'),
    ('apac',   'Asia Pacific (other)',    NULL, 'Asia/Singapore',
        ST_SetSRID(ST_MakeEnvelope(  90.0, -11.0,  150.0,  40.0), 4326),
        'Catch-all APAC region for non-AU/NZ deployments.')
ON CONFLICT (region_code) DO NOTHING;


-- ---------------------------------------------------------------
-- asset_classes
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS asset_classes (
    class_code    TEXT PRIMARY KEY,
    domain        TEXT NOT NULL,
    name          TEXT NOT NULL,
    geometry_type TEXT NOT NULL
        CHECK (geometry_type IN ('point','linestring','polygon','multilinestring','multipolygon')),
    description   TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE asset_classes IS
    'Asset taxonomy. JISP MVP focuses on Jacobs Water domain assets.';

INSERT INTO asset_classes (class_code, domain, name, geometry_type, description) VALUES
    ('water_pipe',            'water', 'Water main / distribution pipe', 'linestring',
        'Buried pressurised water main. Material + age drive condition risk.'),
    ('water_treatment_plant', 'water', 'Water treatment plant',          'point',
        'Facility producing potable water. Throughput and compliance metrics.'),
    ('pump_station',          'water', 'Pump station',                   'point',
        'Pressure / lift pump station on the distribution network.'),
    ('reservoir',             'water', 'Service reservoir / tank',       'polygon',
        'Storage reservoir or treated-water tank.'),
    ('valve',                 'water', 'Valve',                          'point',
        'Inline isolation, control or pressure-reducing valve.'),
    ('hydrant',               'water', 'Fire hydrant',                   'point',
        'Hydrant — operational + fire-flow asset.'),
    ('sensor',                'water', 'In-network sensor',              'point',
        'Pressure, flow, water-quality or level sensor.'),
    ('dam',                   'water', 'Dam',                            'point',
        'Dam structure (NID-style register).'),
    ('catchment',             'water', 'Catchment / watershed',          'polygon',
        'Hydrological catchment polygon.'),
    ('bridge',                'civil', 'Bridge',                         'point',
        'Bridge structure (cross-domain — used for resilience overlays).')
ON CONFLICT (class_code) DO NOTHING;


-- ---------------------------------------------------------------
-- materials
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS materials (
    material_code   TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    family          TEXT NOT NULL,
    typical_life_yr INTEGER,
    description     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE materials IS
    'Construction materials referenced by water + civil assets. '
    'typical_life_yr is an indicative design life used by the GeoAI '
    'condition model when no asset-specific data is available.';

INSERT INTO materials (material_code, name, family, typical_life_yr, description) VALUES
    ('di',   'Ductile iron',             'metallic',  100, 'Modern ductile iron — long life, corrosion-resistant.'),
    ('ci',   'Cast iron',                'metallic',   80, 'Legacy cast iron — common in pre-1980 distribution mains.'),
    ('steel','Steel',                    'metallic',   75, 'Welded steel pipe — large-diameter mains.'),
    ('pvc',  'Polyvinyl chloride',       'plastic',    70, 'PVC pressure pipe — low cost, sensitive to UV and impact.'),
    ('hdpe', 'High-density polyethylene','plastic',   100, 'HDPE — fused joints, flexible, modern preference.'),
    ('mdpe', 'Medium-density polyethylene','plastic',  80, 'MDPE — common UK service pipe material.'),
    ('ac',   'Asbestos cement',          'composite',  50, 'Legacy AC pipe — managed replacement programmes worldwide.'),
    ('conc', 'Concrete',                 'composite',  80, 'Concrete pipe — large diameter, often pre-stressed.'),
    ('cu',   'Copper',                   'metallic',   60, 'Service-pipe copper — rarely on the distribution main.'),
    ('unknown','Unknown / unrecorded',   'unknown',  NULL, 'Material not recorded in source system.')
ON CONFLICT (material_code) DO NOTHING;

COMMIT;
