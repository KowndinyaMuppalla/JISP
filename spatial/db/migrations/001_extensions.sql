-- JISP migration 001: PostgreSQL extensions
--
-- Aligned with the canonical mvp schema (feat/jisp-mvp:spatial/db/schema.sql).
-- Idempotent — safe to re-run against an already-initialised cluster.

BEGIN;

-- Spatial types, operators, indexes, and SRID catalogue.
CREATE EXTENSION IF NOT EXISTS postgis;

-- TimescaleDB powers the `observations` hypertable in migration 004.
-- CASCADE matches the canonical schema's load directive.
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- uuid_generate_v4() is the default for every UUID PK in mvp
-- (assets.asset_id, risk_scores.score_id, inspection_queue.queue_id, …).
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Trigram search powers fuzzy asset-name lookups from the API.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- btree_gist supports compound exclusion constraints on hypertables.
-- Loaded silently if the build has it (most Timescale images do).
DO $$
BEGIN
    PERFORM 1 FROM pg_available_extensions WHERE name = 'btree_gist';
    IF FOUND THEN
        EXECUTE 'CREATE EXTENSION IF NOT EXISTS btree_gist';
    END IF;
END
$$;

COMMIT;
