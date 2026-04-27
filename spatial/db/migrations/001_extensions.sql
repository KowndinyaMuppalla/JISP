-- JISP migration 001: PostgreSQL extensions
--
-- Enables the spatial / time-series / utility extensions JISP relies on.
-- All statements are idempotent so the migration can be re-run safely
-- against an already-initialised cluster.
--
-- Order matters:
--   * postgis must be present before any geometry column is created
--     (migrations 003 and 004 depend on it).
--   * timescaledb must be present before any hypertable is created
--     (migration 004 converts `observations` into one).

BEGIN;

-- Spatial types, operators, indexes, and SRID catalogue.
CREATE EXTENSION IF NOT EXISTS postgis;

-- Topology + raster are not used by current JISP code but several
-- downstream PostGIS functions assume the SRID catalogue lives in
-- a known schema; postgis_topology is loaded lazily only if available
-- to avoid hard-failing on PostGIS builds without it.
DO $$
BEGIN
    PERFORM 1
    FROM pg_available_extensions
    WHERE name = 'postgis_topology';
    IF FOUND THEN
        EXECUTE 'CREATE EXTENSION IF NOT EXISTS postgis_topology';
    END IF;
END
$$;

-- TimescaleDB powers the `observations` hypertable in migration 004.
-- The "ha" image bundled in docker/db.Dockerfile already ships this.
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- btree_gist is required for compound (time, asset_id) constraints
-- on hypertables and for spatial-temporal exclusion constraints.
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- pgcrypto provides gen_random_uuid() for primary keys without
-- needing the older uuid-ossp extension.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Trigram search powers fuzzy asset_code / name lookups from the API.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

COMMIT;
