BEGIN;

CREATE TABLE IF NOT EXISTS regions (
    code            TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    srid            INT  NOT NULL DEFAULT 4326,
    unit_system     TEXT NOT NULL DEFAULT 'metric',
    regulatory_body TEXT,
    country_codes   TEXT[]
);

INSERT INTO regions (code, name, srid, unit_system, regulatory_body, country_codes) VALUES
    ('US',   'United States',       4269, 'imperial', 'EPA/AWWA',  ARRAY['US']),
    ('UK',   'United Kingdom',      27700,'metric',   'EA/Ofwat',  ARRAY['GB']),
    ('ANZ',  'Australia & NZ',      4283, 'metric',   'WSAA/MfE',  ARRAY['AU','NZ']),
    ('APAC', 'Asia Pacific',        4326, 'metric',   'ISO 24510', ARRAY['SG','JP','IN','HK'])
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS asset_classes (
    code          TEXT PRIMARY KEY,
    label         TEXT NOT NULL,
    geometry_type TEXT NOT NULL,
    domain        TEXT NOT NULL DEFAULT 'water'
);

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
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS materials (
    code        TEXT PRIMARY KEY,
    label       TEXT NOT NULL,
    risk_factor FLOAT NOT NULL CHECK (risk_factor BETWEEN 0.0 AND 1.0)
);

INSERT INTO materials (code, label, risk_factor) VALUES
    ('AC',   'Asbestos Cement',    0.90),
    ('CI',   'Cast Iron',          0.70),
    ('CLAY', 'Vitrified Clay',     0.50),
    ('CONC', 'Concrete',           0.50),
    ('DI',   'Ductile Iron',       0.30),
    ('STL',  'Steel',              0.40),
    ('PVC',  'PVC',                0.20),
    ('HDPE', 'HDPE',               0.15),
    ('GRP',  'Glass-Reinforced Plastic', 0.20),
    ('UNK',  'Unknown',            0.60)
ON CONFLICT DO NOTHING;

COMMIT;
