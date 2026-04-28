"""Static structural tests for JISP DB migrations.

The migrations are aligned with the canonical mvp schema shipped on
``feat/jisp-mvp:spatial/db/schema.sql``.

These tests do **not** require a running PostgreSQL cluster. They verify:

* Migrations exist at the documented path and follow the ``NNN_*.sql`` naming.
* Files are discoverable and lexicographically ordered.
* Each migration is wrapped in a single ``BEGIN/COMMIT`` block.
* Required objects (tables, indexes, triggers, hypertable, extensions, views)
  are declared somewhere in the migration set.
* ``IF NOT EXISTS`` / ``ON CONFLICT DO NOTHING`` is used wherever idempotency
  is asserted in the migration's docstring.
* The migration runner discovers files in deterministic order and computes
  stable checksums.

Live SQL execution is covered separately by a Docker-based integration test
that is skipped when ``JISP_DATABASE_URL`` is not set.
"""

from __future__ import annotations

import re

import pytest

from scripts.bootstrap_db import (
    MIGRATIONS_DIR,
    Migration,
    discover_migrations,
)


# ---------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------

@pytest.fixture(scope="module")
def migrations() -> list[Migration]:
    return discover_migrations()


@pytest.fixture(scope="module")
def migrations_by_name(migrations: list[Migration]) -> dict[str, Migration]:
    return {m.filename: m for m in migrations}


@pytest.fixture(scope="module")
def all_sql(migrations: list[Migration]) -> str:
    """Concatenated SQL across every migration, lower-cased for grepping."""
    return "\n".join(m.read_sql() for m in migrations).lower()


# ---------------------------------------------------------------
# Discovery / ordering
# ---------------------------------------------------------------

class TestDiscovery:

    def test_migrations_directory_exists(self) -> None:
        assert MIGRATIONS_DIR.is_dir(), (
            f"Expected migrations directory at {MIGRATIONS_DIR}"
        )

    def test_at_least_six_migrations(self, migrations: list[Migration]) -> None:
        assert len(migrations) >= 6, (
            f"Expected at least 6 migrations, found {len(migrations)}"
        )

    def test_migration_filenames_follow_convention(
        self, migrations: list[Migration]
    ) -> None:
        pattern = re.compile(r"^\d{3}_[a-z0-9_]+\.sql$")
        bad = [m.filename for m in migrations if not pattern.match(m.filename)]
        assert not bad, f"Migrations violating NNN_*.sql convention: {bad}"

    def test_migration_filenames_are_unique_prefixes(
        self, migrations: list[Migration]
    ) -> None:
        prefixes = [m.filename.split("_", 1)[0] for m in migrations]
        assert len(set(prefixes)) == len(prefixes), (
            f"Duplicate NNN prefixes: {prefixes}"
        )

    def test_migrations_are_lexicographically_sorted(
        self, migrations: list[Migration]
    ) -> None:
        names = [m.filename for m in migrations]
        assert names == sorted(names)

    def test_checksum_is_sha256_hex(self, migrations: list[Migration]) -> None:
        for m in migrations:
            assert len(m.checksum) == 64
            assert re.fullmatch(r"[0-9a-f]{64}", m.checksum)

    def test_checksum_is_stable(self) -> None:
        """Re-running discover_migrations yields identical checksums."""
        first  = {m.filename: m.checksum for m in discover_migrations()}
        second = {m.filename: m.checksum for m in discover_migrations()}
        assert first == second


# ---------------------------------------------------------------
# Transactional wrapping
# ---------------------------------------------------------------

class TestTransactionalShape:

    def test_each_migration_starts_with_begin(
        self, migrations: list[Migration]
    ) -> None:
        for m in migrations:
            sql = m.read_sql()
            assert re.search(r"(?im)^\s*BEGIN\s*;", sql), (
                f"{m.filename} does not start with BEGIN;"
            )

    def test_each_migration_ends_with_commit(
        self, migrations: list[Migration]
    ) -> None:
        for m in migrations:
            sql = m.read_sql()
            assert re.search(r"(?im)^\s*COMMIT\s*;\s*$", sql.rstrip() + "\n"), (
                f"{m.filename} does not end with COMMIT;"
            )

    def test_no_unbalanced_dollar_quoting(
        self, migrations: list[Migration]
    ) -> None:
        for m in migrations:
            sql = m.read_sql()
            count = sql.count("$$")
            assert count % 2 == 0, (
                f"{m.filename} has unbalanced $$ blocks (count={count})"
            )


# ---------------------------------------------------------------
# 001 — extensions (matches mvp canonical schema)
# ---------------------------------------------------------------

class TestExtensions:

    def test_postgis_extension(
        self, migrations_by_name: dict[str, Migration]
    ) -> None:
        sql = migrations_by_name["001_extensions.sql"].read_sql().lower()
        assert "create extension if not exists postgis" in sql

    def test_timescaledb_extension(
        self, migrations_by_name: dict[str, Migration]
    ) -> None:
        sql = migrations_by_name["001_extensions.sql"].read_sql().lower()
        assert "create extension if not exists timescaledb" in sql

    def test_uuid_ossp_extension(
        self, migrations_by_name: dict[str, Migration]
    ) -> None:
        sql = migrations_by_name["001_extensions.sql"].read_sql().lower()
        assert 'create extension if not exists "uuid-ossp"' in sql


# ---------------------------------------------------------------
# 002 — reference tables (mvp shape: regions.code, asset_classes.code)
# ---------------------------------------------------------------

class TestReferenceTables:

    def test_regions_table(
        self, migrations_by_name: dict[str, Migration]
    ) -> None:
        sql = migrations_by_name["002_reference_tables.sql"].read_sql().lower()
        assert "create table if not exists regions" in sql
        assert re.search(r"code\s+text\s+primary\s+key", sql)
        assert "country_codes" in sql

    def test_asset_classes_table(
        self, migrations_by_name: dict[str, Migration]
    ) -> None:
        sql = migrations_by_name["002_reference_tables.sql"].read_sql().lower()
        assert "create table if not exists asset_classes" in sql
        assert "geometry_type" in sql

    def test_no_separate_materials_table(
        self, migrations_by_name: dict[str, Migration]
    ) -> None:
        # mvp folds material into a free-text column on assets; there is
        # no separate `materials` reference table.
        sql = migrations_by_name["002_reference_tables.sql"].read_sql().lower()
        assert "create table if not exists materials" not in sql

    @pytest.mark.parametrize(
        "region_code",
        ["us", "uk", "anz", "apac"],
    )
    def test_seeded_regions(
        self,
        migrations_by_name: dict[str, Migration],
        region_code: str,
    ) -> None:
        sql = migrations_by_name["002_reference_tables.sql"].read_sql().lower()
        assert f"'{region_code}'" in sql, (
            f"Region {region_code!r} not seeded in 002_reference_tables.sql"
        )

    @pytest.mark.parametrize(
        "class_code",
        [
            "wtp", "wwtp", "pump", "reservoir", "dam",
            "pipe_w", "pipe_s", "pipe_st",
            "valve", "hydrant", "meter", "manhole",
            "sensor", "flood_z", "catchment",
        ],
    )
    def test_seeded_asset_classes(
        self,
        migrations_by_name: dict[str, Migration],
        class_code: str,
    ) -> None:
        sql = migrations_by_name["002_reference_tables.sql"].read_sql().lower()
        assert f"'{class_code}'" in sql

    def test_seeds_are_idempotent(
        self, migrations_by_name: dict[str, Migration]
    ) -> None:
        sql = migrations_by_name["002_reference_tables.sql"].read_sql().lower()
        assert sql.count("on conflict") >= 2, (
            "INSERTs in 002 should use ON CONFLICT DO NOTHING for idempotency."
        )


# ---------------------------------------------------------------
# 003 — assets table (mvp shape: asset_id UUID, asset_class, risk_tier 0-100)
# ---------------------------------------------------------------

class TestAssetsTable:

    def test_assets_table(
        self, migrations_by_name: dict[str, Migration]
    ) -> None:
        sql = migrations_by_name["003_assets_table.sql"].read_sql().lower()
        assert "create table if not exists assets" in sql

    def test_asset_id_is_uuid(
        self, migrations_by_name: dict[str, Migration]
    ) -> None:
        sql = migrations_by_name["003_assets_table.sql"].read_sql().lower()
        assert "asset_id" in sql
        assert "uuid_generate_v4()" in sql

    def test_geometry_is_4326(
        self, migrations_by_name: dict[str, Migration]
    ) -> None:
        sql = migrations_by_name["003_assets_table.sql"].read_sql().lower()
        assert "geometry(geometry, 4326)" in sql

    def test_assets_has_spatial_gist_index(
        self, migrations_by_name: dict[str, Migration]
    ) -> None:
        sql = migrations_by_name["003_assets_table.sql"].read_sql().lower()
        assert "using gist (geometry)" in sql

    def test_assets_foreign_keys(
        self, migrations_by_name: dict[str, Migration]
    ) -> None:
        sql = migrations_by_name["003_assets_table.sql"].read_sql().lower()
        assert "references regions(code)" in sql
        assert "references asset_classes(code)" in sql

    def test_risk_tier_enum(
        self, migrations_by_name: dict[str, Migration]
    ) -> None:
        sql = migrations_by_name["003_assets_table.sql"].read_sql().lower()
        for tier in ("critical", "high", "medium", "low", "unknown"):
            assert f"'{tier}'" in sql

    def test_condition_score_bounded_0_100(
        self, migrations_by_name: dict[str, Migration]
    ) -> None:
        sql = migrations_by_name["003_assets_table.sql"].read_sql().lower()
        assert "condition_score between 0 and 100" in sql

    def test_install_year_check(
        self, migrations_by_name: dict[str, Migration]
    ) -> None:
        sql = migrations_by_name["003_assets_table.sql"].read_sql().lower()
        assert "install_year" in sql
        assert "between 1700 and 2100" in sql

    def test_is_active_default_true(
        self, migrations_by_name: dict[str, Migration]
    ) -> None:
        sql = migrations_by_name["003_assets_table.sql"].read_sql().lower()
        assert "is_active" in sql
        assert "default true" in sql


# ---------------------------------------------------------------
# 004 — observations + geoai result tables (mvp shape)
# ---------------------------------------------------------------

class TestObservationsAndGeoAITables:

    @pytest.mark.parametrize(
        "table",
        [
            "observations",
            "asset_alerts",
            "risk_scores",
            "cluster_zones",
            "inspection_queue",
            "explanation_log",
        ],
    )
    def test_required_tables(
        self,
        migrations_by_name: dict[str, Migration],
        table: str,
    ) -> None:
        sql = migrations_by_name["004_observations_geoai.sql"].read_sql().lower()
        assert f"create table if not exists {table}" in sql

    def test_observations_is_hypertable(
        self, migrations_by_name: dict[str, Migration]
    ) -> None:
        sql = migrations_by_name["004_observations_geoai.sql"].read_sql().lower()
        assert "create_hypertable(" in sql
        assert "'observations'" in sql
        assert "if_not_exists" in sql

    def test_observations_quality_flag_enum(
        self, migrations_by_name: dict[str, Migration]
    ) -> None:
        sql = migrations_by_name["004_observations_geoai.sql"].read_sql().lower()
        assert "quality_flag" in sql
        assert "in (0, 1, 2)" in sql or "in (0,1,2)" in sql

    def test_risk_scores_uses_score_id_uuid_pk(
        self, migrations_by_name: dict[str, Migration]
    ) -> None:
        sql = migrations_by_name["004_observations_geoai.sql"].read_sql().lower()
        assert re.search(r"score_id\s+uuid\s+primary\s+key", sql)

    def test_risk_score_bounded_0_100(
        self, migrations_by_name: dict[str, Migration]
    ) -> None:
        sql = migrations_by_name["004_observations_geoai.sql"].read_sql().lower()
        assert "risk_score between 0 and 100" in sql

    def test_risk_tier_check_in_risk_scores(
        self, migrations_by_name: dict[str, Migration]
    ) -> None:
        sql = migrations_by_name["004_observations_geoai.sql"].read_sql().lower()
        for tier in ("critical", "high", "medium", "low"):
            assert f"'{tier}'" in sql

    def test_alert_severity_int_range(
        self, migrations_by_name: dict[str, Migration]
    ) -> None:
        sql = migrations_by_name["004_observations_geoai.sql"].read_sql().lower()
        assert "severity" in sql
        assert "between 1 and 5" in sql

    def test_cluster_zones_polygon_geometry(
        self, migrations_by_name: dict[str, Migration]
    ) -> None:
        sql = migrations_by_name["004_observations_geoai.sql"].read_sql().lower()
        assert "geometry(polygon, 4326)" in sql

    def test_inspection_queue_status_enum(
        self, migrations_by_name: dict[str, Migration]
    ) -> None:
        sql = migrations_by_name["004_observations_geoai.sql"].read_sql().lower()
        for st in ("pending", "scheduled", "completed", "cancelled"):
            assert f"'{st}'" in sql

    def test_explanation_log_default_model(
        self, migrations_by_name: dict[str, Migration]
    ) -> None:
        sql = migrations_by_name["004_observations_geoai.sql"].read_sql().lower()
        assert "default 'llama3.2'" in sql


# ---------------------------------------------------------------
# 005 — region + risk-enriched views (mvp v_* names)
# ---------------------------------------------------------------

class TestRegionViews:

    @pytest.mark.parametrize(
        "view",
        [
            "v_assets_us",
            "v_assets_uk",
            "v_assets_anz",
            "v_assets_apac",
            "v_assets_with_risk",
            "v_inspection_queue_full",
        ],
    )
    def test_views_declared(
        self,
        migrations_by_name: dict[str, Migration],
        view: str,
    ) -> None:
        sql = migrations_by_name["005_region_views.sql"].read_sql().lower()
        assert f"create or replace view {view}" in sql

    def test_views_drop_first_for_idempotency(
        self, migrations_by_name: dict[str, Migration]
    ) -> None:
        sql = migrations_by_name["005_region_views.sql"].read_sql().lower()
        assert sql.count("drop view if exists") >= 5


# ---------------------------------------------------------------
# 006 — indexes + triggers
# ---------------------------------------------------------------

class TestIndexesAndTriggers:

    def test_trgm_index_on_assets_name(
        self, migrations_by_name: dict[str, Migration]
    ) -> None:
        sql = migrations_by_name["006_indexes_triggers.sql"].read_sql().lower()
        assert "gin (name gin_trgm_ops)" in sql

    def test_jsonb_gin_indexes(
        self, migrations_by_name: dict[str, Migration]
    ) -> None:
        sql = migrations_by_name["006_indexes_triggers.sql"].read_sql().lower()
        assert "jsonb_path_ops" in sql

    def test_updated_at_trigger(
        self, migrations_by_name: dict[str, Migration]
    ) -> None:
        sql = migrations_by_name["006_indexes_triggers.sql"].read_sql().lower()
        assert "function trg_update_ts" in sql
        assert "trigger trg_assets_ts" in sql

    def test_alert_resolved_trigger(
        self, migrations_by_name: dict[str, Migration]
    ) -> None:
        sql = migrations_by_name["006_indexes_triggers.sql"].read_sql().lower()
        assert "function trg_alert_resolved" in sql

    def test_inspection_queue_close_trigger(
        self, migrations_by_name: dict[str, Migration]
    ) -> None:
        sql = migrations_by_name["006_indexes_triggers.sql"].read_sql().lower()
        assert "function trg_inspection_queue_close" in sql

    def test_triggers_drop_first(
        self, migrations_by_name: dict[str, Migration]
    ) -> None:
        sql = migrations_by_name["006_indexes_triggers.sql"].read_sql().lower()
        assert sql.count("drop trigger if exists") >= 3


# ---------------------------------------------------------------
# Cross-cutting invariants
# ---------------------------------------------------------------

class TestCrossCutting:

    def test_no_srid_other_than_4326_on_geometry_columns(self, all_sql: str) -> None:
        # Geometry columns must always pin 4326. The regions catalogue table
        # *records* working SRIDs (e.g. 4269 for US) as data, which is fine —
        # this check is scoped to GEOMETRY(...) column declarations only.
        for srid in re.findall(r"\bgeometry\(\w+,\s*(\d{4})\)", all_sql):
            assert int(srid) == 4326, f"GEOMETRY column with non-4326 SRID: {srid}"

    def test_runner_module_imports(self) -> None:
        from scripts import bootstrap_db  # noqa: F401

    def test_runner_dry_run_lists_migrations(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from scripts.bootstrap_db import main

        rc = main(["--dry-run"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "001_extensions.sql" in out
        assert "006_indexes_triggers.sql" in out
