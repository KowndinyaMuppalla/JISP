-- JISP Complete Schema v1.0 (MVP)
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS regions (
    code TEXT PRIMARY KEY, name TEXT NOT NULL, srid INT NOT NULL DEFAULT 4326,
    unit_system TEXT NOT NULL DEFAULT 'metric', regulatory_body TEXT, country_codes TEXT[]
);
INSERT INTO regions VALUES
  ('US','United States',4269,'imperial','EPA/AWWA',ARRAY['US']),
  ('UK','United Kingdom',27700,'metric','EA/Ofwat',ARRAY['GB']),
  ('ANZ','Australia & NZ',4283,'metric','WSAA/MfE',ARRAY['AU','NZ']),
  ('APAC','Asia Pacific',4326,'metric','ISO 24510',ARRAY['SG','JP','IN','HK'])
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS asset_classes (
    code TEXT PRIMARY KEY, label TEXT NOT NULL, geometry_type TEXT NOT NULL, domain TEXT NOT NULL DEFAULT 'water'
);
INSERT INTO asset_classes VALUES
  ('WTP','Water Treatment Plant','Point','water'),('WWTP','Wastewater Treatment Plant','Point','wastewater'),
  ('PUMP','Pump Station','Point','water'),('RESERVOIR','Reservoir','Polygon','water'),
  ('DAM','Dam','Point','water'),('PIPE_W','Water Main','LineString','water'),
  ('PIPE_S','Sewer Main','LineString','wastewater'),('PIPE_ST','Stormwater Drain','LineString','stormwater'),
  ('VALVE','Valve','Point','water'),('HYDRANT','Fire Hydrant','Point','water'),
  ('METER','Water Meter','Point','water'),('MANHOLE','Manhole','Point','wastewater'),
  ('SENSOR','Monitoring Sensor','Point','water'),('FLOOD_Z','Flood Risk Zone','Polygon','flood'),
  ('CATCHMENT','Drainage Catchment','Polygon','stormwater')
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS assets (
    asset_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(), external_id TEXT,
    region_code TEXT NOT NULL REFERENCES regions(code), asset_class TEXT NOT NULL REFERENCES asset_classes(code),
    name TEXT NOT NULL, description TEXT, owner TEXT,
    geometry GEOMETRY(Geometry,4326) NOT NULL,
    material TEXT, diameter_mm FLOAT, length_m FLOAT, capacity_ml FLOAT,
    elevation_m FLOAT, depth_m FLOAT, pressure_zone TEXT, install_year INT,
    condition_score FLOAT CHECK (condition_score BETWEEN 0 AND 100),
    risk_tier TEXT CHECK (risk_tier IN ('critical','high','medium','low','unknown')) DEFAULT 'unknown',
    last_inspected DATE, next_inspection DATE, is_critical BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE, attributes JSONB NOT NULL DEFAULT '{}',
    source TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_assets_geom   ON assets USING GIST (geometry);
CREATE INDEX IF NOT EXISTS idx_assets_region ON assets (region_code);
CREATE INDEX IF NOT EXISTS idx_assets_class  ON assets (asset_class);
CREATE INDEX IF NOT EXISTS idx_assets_risk   ON assets (risk_tier);
CREATE INDEX IF NOT EXISTS idx_assets_name   ON assets USING GIN (name gin_trgm_ops);
CREATE OR REPLACE FUNCTION trg_update_ts() RETURNS TRIGGER AS $$ BEGIN NEW.updated_at=now(); RETURN NEW; END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_assets_ts ON assets;
CREATE TRIGGER trg_assets_ts BEFORE UPDATE ON assets FOR EACH ROW EXECUTE FUNCTION trg_update_ts();

CREATE TABLE IF NOT EXISTS observations (
    time TIMESTAMPTZ NOT NULL, asset_id UUID NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
    metric TEXT NOT NULL, value DOUBLE PRECISION NOT NULL, unit TEXT,
    quality_flag SMALLINT NOT NULL DEFAULT 0 CHECK (quality_flag IN (0,1,2)), source TEXT NOT NULL DEFAULT 'sensor'
);
SELECT create_hypertable('observations','time',chunk_time_interval=>INTERVAL '7 days',if_not_exists=>TRUE);
CREATE INDEX IF NOT EXISTS idx_obs_asset_time ON observations (asset_id, time DESC);

CREATE TABLE IF NOT EXISTS asset_alerts (
    alert_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(), asset_id UUID NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
    time TIMESTAMPTZ NOT NULL DEFAULT now(), alert_type TEXT NOT NULL, severity INT NOT NULL CHECK (severity BETWEEN 1 AND 5),
    message TEXT NOT NULL, metric TEXT, value FLOAT, threshold FLOAT, resolved BOOLEAN NOT NULL DEFAULT FALSE, resolved_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_alerts_asset ON asset_alerts (asset_id, time DESC);

CREATE TABLE IF NOT EXISTS risk_scores (
    score_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(), asset_id UUID NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
    scored_at TIMESTAMPTZ NOT NULL DEFAULT now(), risk_score FLOAT NOT NULL CHECK (risk_score BETWEEN 0 AND 100),
    risk_tier TEXT NOT NULL CHECK (risk_tier IN ('critical','high','medium','low')),
    model_version TEXT NOT NULL DEFAULT 'v1', shap_values JSONB, features_used JSONB,
    anomaly_flag BOOLEAN NOT NULL DEFAULT FALSE, anomaly_types TEXT[], notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_risk_asset ON risk_scores (asset_id, scored_at DESC);

CREATE TABLE IF NOT EXISTS cluster_zones (
    zone_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(), region_code TEXT REFERENCES regions(code),
    geometry GEOMETRY(Polygon,4326) NOT NULL, cluster_id INT NOT NULL, asset_count INT,
    avg_risk FLOAT, dominant_class TEXT, computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_zones_geom ON cluster_zones USING GIST (geometry);

CREATE TABLE IF NOT EXISTS inspection_queue (
    queue_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(), asset_id UUID NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
    region_code TEXT REFERENCES regions(code), priority_rank INT NOT NULL, priority_score FLOAT NOT NULL,
    risk_tier TEXT, reason_codes TEXT[], recommended_date DATE,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','scheduled','completed','cancelled'))
);
CREATE INDEX IF NOT EXISTS idx_queue_rank ON inspection_queue (priority_rank);

CREATE TABLE IF NOT EXISTS explanation_log (
    log_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(), asset_id UUID REFERENCES assets(asset_id) ON DELETE SET NULL,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(), template TEXT NOT NULL, context JSONB,
    explanation TEXT NOT NULL, model TEXT NOT NULL DEFAULT 'llama3.2', latency_ms INT
);

CREATE OR REPLACE VIEW v_assets_us   AS SELECT * FROM assets WHERE region_code='US'   AND is_active=TRUE;
CREATE OR REPLACE VIEW v_assets_uk   AS SELECT * FROM assets WHERE region_code='UK'   AND is_active=TRUE;
CREATE OR REPLACE VIEW v_assets_anz  AS SELECT * FROM assets WHERE region_code='ANZ'  AND is_active=TRUE;
CREATE OR REPLACE VIEW v_assets_apac AS SELECT * FROM assets WHERE region_code='APAC' AND is_active=TRUE;

CREATE OR REPLACE VIEW v_assets_with_risk AS
SELECT a.*, rs.risk_score, rs.risk_tier AS ai_risk_tier, rs.anomaly_flag, rs.scored_at
FROM assets a LEFT JOIN LATERAL (
    SELECT risk_score, risk_tier, anomaly_flag, scored_at FROM risk_scores
    WHERE asset_id=a.asset_id ORDER BY scored_at DESC LIMIT 1
) rs ON TRUE WHERE a.is_active=TRUE;

CREATE OR REPLACE VIEW v_inspection_queue_full AS
SELECT iq.*, a.name, a.asset_class, a.geometry, a.region_code,
       a.condition_score, a.last_inspected, a.material, a.install_year
FROM inspection_queue iq JOIN assets a ON a.asset_id=iq.asset_id
WHERE iq.status='pending' ORDER BY iq.priority_rank;
