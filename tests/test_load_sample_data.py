"""Static tests for the sample-data seed generator.

These tests exercise the *pure* generators in ``scripts.load_sample_data``
— no PostgreSQL needed. The DB-writing path (``apply()``) is covered by
the migrations integration job which spins up a real cluster.
"""

from __future__ import annotations

import re

import pytest

from scripts.load_sample_data import (
    ASSET_CLASS_PROFILES,
    DEFAULT_CLASS_WEIGHTS,
    REGION_WEIGHTS,
    RISK_TIERS,
    QUALITY_FLAGS,
    generate_all,
    generate_assets,
    generate_initial_risk_scores,
    generate_observations,
)


# ---------------------------------------------------------------
# Asset generator
# ---------------------------------------------------------------

class TestGenerateAssets:

    def test_count(self) -> None:
        rows = generate_assets(count=200, seed=42)
        assert len(rows) == 200

    def test_count_is_honoured(self) -> None:
        for n in (10, 50, 500):
            assert len(generate_assets(count=n, seed=42)) == n

    def test_deterministic(self) -> None:
        a = generate_assets(count=50, seed=42)
        b = generate_assets(count=50, seed=42)
        assert a == b

    def test_different_seed_produces_different_data(self) -> None:
        a = generate_assets(count=50, seed=42)
        b = generate_assets(count=50, seed=43)
        assert a != b

    def test_external_id_unique(self) -> None:
        rows = generate_assets(count=200, seed=42)
        ext_ids = [r["external_id"] for r in rows]
        assert len(set(ext_ids)) == len(ext_ids)

    def test_all_regions_present_at_scale(self) -> None:
        rows = generate_assets(count=300, seed=42)
        regions = {r["region_code"] for r in rows}
        assert regions == set(REGION_WEIGHTS.keys())

    def test_region_codes_are_valid(self) -> None:
        rows = generate_assets(count=200, seed=42)
        for r in rows:
            assert r["region_code"] in REGION_WEIGHTS

    def test_asset_class_codes_are_valid(self) -> None:
        valid = {p[0] for p in ASSET_CLASS_PROFILES}
        rows = generate_assets(count=200, seed=42)
        for r in rows:
            assert r["asset_class"] in valid

    def test_asset_classes_match_default_weights(self) -> None:
        # Every weighted class is also a profile.
        profile_codes = {p[0] for p in ASSET_CLASS_PROFILES}
        assert set(DEFAULT_CLASS_WEIGHTS) <= profile_codes

    @pytest.mark.parametrize("seed", [42, 99, 17])
    def test_geometry_wkt_uses_srid_4326(self, seed: int) -> None:
        rows = generate_assets(count=120, seed=seed)
        for r in rows:
            assert r["geometry_wkt"].startswith("SRID=4326;")
            assert re.match(r"^SRID=4326;(POINT|LINESTRING|POLYGON)\(",
                            r["geometry_wkt"])

    def test_geometry_type_matches_class_profile(self) -> None:
        profile_geom = {p[0]: p[1] for p in ASSET_CLASS_PROFILES}
        rows = generate_assets(count=200, seed=42)
        for r in rows:
            wkt = r["geometry_wkt"]
            expected = profile_geom[r["asset_class"]]
            assert expected.upper() in wkt, (
                f"{r['asset_class']} should produce {expected} WKT, got {wkt[:40]}"
            )

    def test_condition_score_in_range(self) -> None:
        rows = generate_assets(count=300, seed=42)
        for r in rows:
            assert 0.0 <= r["condition_score"] <= 100.0

    def test_risk_tier_is_valid_enum(self) -> None:
        rows = generate_assets(count=200, seed=42)
        for r in rows:
            assert r["risk_tier"] in RISK_TIERS

    def test_install_year_in_plausible_range(self) -> None:
        rows = generate_assets(count=200, seed=42)
        for r in rows:
            if r["install_year"] is not None:
                assert 1925 <= r["install_year"] <= 2024

    def test_diameter_only_set_for_pipe_like_classes(self) -> None:
        pipe_like = {"PIPE_W", "PIPE_S", "PIPE_ST", "VALVE", "HYDRANT",
                     "METER", "MANHOLE"}
        rows = generate_assets(count=200, seed=42)
        for r in rows:
            if r["asset_class"] in pipe_like:
                assert r["diameter_mm"] is not None
            else:
                assert r["diameter_mm"] is None or r["diameter_mm"] == 0

    def test_required_columns_present(self) -> None:
        required = {
            "external_id", "region_code", "asset_class", "name",
            "geometry_wkt", "install_year", "condition_score",
            "risk_tier", "is_critical", "is_active",
            "attributes", "source",
        }
        rows = generate_assets(count=10, seed=42)
        for r in rows:
            missing = required - set(r.keys())
            assert not missing, f"Missing keys: {missing}"

    def test_source_is_seed(self) -> None:
        rows = generate_assets(count=10, seed=42)
        assert all(r["source"] == "seed" for r in rows)


# ---------------------------------------------------------------
# Observation generator
# ---------------------------------------------------------------

class TestGenerateObservations:

    def test_only_for_sensor_and_meter_assets(self) -> None:
        assets = generate_assets(count=200, seed=42)
        obs = generate_observations(assets, days=2, seed=42)
        eligible_ext = {a["external_id"] for a in assets
                        if a["asset_class"] in {"SENSOR", "METER"}}
        for o in obs:
            assert o["external_id"] in eligible_ext

    def test_two_metrics_per_asset_per_hour(self) -> None:
        assets = generate_assets(count=200, seed=42)
        days = 3
        obs = generate_observations(assets, days=days, seed=42)
        eligible = [a for a in assets
                    if a["asset_class"] in {"SENSOR", "METER"}]
        assert len(obs) == len(eligible) * days * 24 * 2

    def test_quality_flag_in_enum(self) -> None:
        assets = generate_assets(count=200, seed=42)
        obs = generate_observations(assets, days=1, seed=42)
        for o in obs:
            assert o["quality_flag"] in QUALITY_FLAGS

    def test_metric_names_are_canonical(self) -> None:
        assets = generate_assets(count=200, seed=42)
        obs = generate_observations(assets, days=1, seed=42)
        metrics = {o["metric"] for o in obs}
        assert metrics == {"pressure_psi", "flow_lps"}

    def test_deterministic(self) -> None:
        assets = generate_assets(count=80, seed=42)
        a = generate_observations(assets, days=2, seed=42)
        b = generate_observations(assets, days=2, seed=42)
        assert a == b

    def test_zero_days_returns_empty(self) -> None:
        assets = generate_assets(count=80, seed=42)
        assert generate_observations(assets, days=0, seed=42) == []


# ---------------------------------------------------------------
# Risk-score generator
# ---------------------------------------------------------------

class TestGenerateInitialRiskScores:

    def test_score_in_0_100_range(self) -> None:
        assets = generate_assets(count=200, seed=42)
        scores = generate_initial_risk_scores(assets, seed=42)
        for s in scores:
            assert 0.0 <= s["risk_score"] <= 100.0

    def test_tier_is_valid_enum(self) -> None:
        assets = generate_assets(count=200, seed=42)
        scores = generate_initial_risk_scores(assets, seed=42)
        for s in scores:
            assert s["risk_tier"] in RISK_TIERS

    def test_high_critical_assets_always_seeded(self) -> None:
        # Every asset whose generated tier is high or critical should
        # appear in the initial scores list (the random sample only
        # sweeps in additional medium/low rows).
        assets = generate_assets(count=200, seed=42)
        scores = generate_initial_risk_scores(assets, seed=42)
        scored_ext = {s["external_id"] for s in scores}
        for a in assets:
            if a["risk_tier"] in {"high", "critical"}:
                assert a["external_id"] in scored_ext

    def test_deterministic(self) -> None:
        assets = generate_assets(count=120, seed=42)
        a = generate_initial_risk_scores(assets, seed=42)
        b = generate_initial_risk_scores(assets, seed=42)
        assert a == b


# ---------------------------------------------------------------
# Bundled generate_all
# ---------------------------------------------------------------

class TestGenerateAll:

    def test_bundles_all_three_streams(self) -> None:
        batch = generate_all(asset_count=80, seed=42, observation_days=2)
        assert len(batch.assets) == 80
        assert len(batch.observations) > 0
        assert len(batch.risk_scores) > 0

    def test_observation_days_zero_skips(self) -> None:
        batch = generate_all(asset_count=40, seed=42, observation_days=0)
        assert batch.observations == []

    def test_deterministic(self) -> None:
        a = generate_all(asset_count=50, seed=42, observation_days=1)
        b = generate_all(asset_count=50, seed=42, observation_days=1)
        assert a.assets == b.assets
        assert a.observations == b.observations
        assert a.risk_scores == b.risk_scores


# ---------------------------------------------------------------
# CLI
# ---------------------------------------------------------------

class TestCli:

    def test_dry_run_lists_summary(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from scripts.load_sample_data import main

        rc = main(["--dry-run", "--count", "30", "--observation-days", "1"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Generated 30 assets" in out
        assert "Assets per region" in out
        assert "Assets per class" in out

    def test_dry_run_no_observations(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from scripts.load_sample_data import main

        rc = main(["--dry-run", "--count", "20", "--no-observations"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "0 observations" in out
