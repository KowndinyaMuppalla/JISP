"""Seed JISP with realistic synthetic assets, observations, and risk scores.

Targets the canonical mvp schema (see ``spatial/db/migrations/``).
The generator produces deterministic data (same seed -> same rows) so the
seed is reproducible across machines and re-runnable.

Usage
-----
    # Dry run (no DB required)
    python -m scripts.load_sample_data --dry-run

    # Real run against a configured cluster
    python -m scripts.load_sample_data \\
        --dsn postgresql://jisp:jisp@localhost:5432/jisp

    # or via environment
    JISP_DATABASE_URL=postgresql://... python -m scripts.load_sample_data

Idempotency
-----------
On a real run, every row this script writes carries ``source='seed'``.
The script first deletes existing ``source='seed'`` rows from
``observations``, ``risk_scores``, and ``assets`` (in dependency order)
before re-inserting the fresh batch, so re-running is safe.

Strict scope: this module only writes to the database. It does not
import the API, GeoAI, or reasoning layers.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import random
import sys
from dataclasses import dataclass
from typing import Sequence

logger = logging.getLogger("jisp.load_sample_data")

# ---------------------------------------------------------------
# Constants — anchored against migrations 002 + 003
# ---------------------------------------------------------------

# Anchor cities per region (approximate centroids, WGS84). Generated
# assets cluster around these so a map view is recognisable.
ANCHORS: dict[str, list[tuple[str, float, float]]] = {
    "US":   [("Boston",     -71.058, 42.358),
             ("Chicago",    -87.629, 41.878),
             ("Denver",    -104.991, 39.740)],
    "UK":   [("London",      -0.128, 51.507),
             ("Manchester",  -2.244, 53.483)],
    "ANZ":  [("Sydney",     151.209, -33.868),
             ("Melbourne",  144.963, -37.814),
             ("Auckland",   174.763, -36.848)],
    "APAC": [("Singapore",  103.819,   1.352)],
}

# (asset_class, geometry_type, plausible_materials, diameter_range_mm,
#  length_range_m, capacity_ml_range, depth_range_m)
ASSET_CLASS_PROFILES: list[tuple[str, str, list[str], tuple[int,int],
                                  tuple[int,int], tuple[float,float],
                                  tuple[float,float]]] = [
    ("PIPE_W",    "LineString", ["Ductile Iron", "PVC", "HDPE", "Cast Iron", "Steel"],
                                (100, 600),  (80, 1500), (0.0, 0.0), (0.6, 2.5)),
    ("PIPE_S",    "LineString", ["Concrete", "PVC", "Vitrified Clay", "HDPE"],
                                (150, 900),  (80, 1500), (0.0, 0.0), (1.0, 4.0)),
    ("PIPE_ST",   "LineString", ["Concrete", "HDPE", "PVC"],
                                (200, 1200), (80, 1500), (0.0, 0.0), (0.8, 3.0)),
    ("WTP",       "Point",      ["Concrete", "Steel"],
                                (0, 0),      (0, 0),     (50.0, 800.0), (0.0, 0.0)),
    ("WWTP",      "Point",      ["Concrete", "Steel"],
                                (0, 0),      (0, 0),     (40.0, 600.0), (0.0, 0.0)),
    ("PUMP",      "Point",      ["Steel", "Cast Iron"],
                                (0, 0),      (0, 0),     (1.0, 50.0),  (0.0, 0.0)),
    ("RESERVOIR", "Polygon",    ["Concrete", "Steel"],
                                (0, 0),      (0, 0),     (5.0, 250.0), (0.0, 0.0)),
    ("DAM",       "Point",      ["Concrete"],
                                (0, 0),      (0, 0),     (100.0, 5000.0), (0.0, 0.0)),
    ("VALVE",     "Point",      ["Ductile Iron", "Steel", "Brass"],
                                (50, 600),   (0, 0),     (0.0, 0.0),    (0.5, 2.5)),
    ("HYDRANT",   "Point",      ["Ductile Iron"],
                                (75, 150),   (0, 0),     (0.0, 0.0),    (0.6, 1.2)),
    ("METER",     "Point",      ["Brass", "Composite"],
                                (15, 100),   (0, 0),     (0.0, 0.0),    (0.0, 0.0)),
    ("MANHOLE",   "Point",      ["Concrete"],
                                (600, 1200), (0, 0),     (0.0, 0.0),    (1.5, 6.0)),
    ("SENSOR",    "Point",      [],
                                (0, 0),      (0, 0),     (0.0, 0.0),    (0.0, 0.0)),
    ("FLOOD_Z",   "Polygon",    [],
                                (0, 0),      (0, 0),     (0.0, 0.0),    (0.0, 0.0)),
    ("CATCHMENT", "Polygon",    [],
                                (0, 0),      (0, 0),     (0.0, 0.0),    (0.0, 0.0)),
]

# Mix that keeps pipes dominant (matches a real water-network inventory).
DEFAULT_CLASS_WEIGHTS: dict[str, float] = {
    "PIPE_W":    20.0,
    "PIPE_S":     8.0,
    "PIPE_ST":    5.0,
    "VALVE":      9.0,
    "HYDRANT":    8.0,
    "METER":      6.0,
    "MANHOLE":    6.0,
    "SENSOR":     5.0,
    "PUMP":       4.0,
    "WTP":        2.0,
    "WWTP":       2.0,
    "RESERVOIR":  3.0,
    "DAM":        1.0,
    "FLOOD_Z":    1.0,
    "CATCHMENT":  1.0,
}

REGION_WEIGHTS: dict[str, float] = {"US": 35, "UK": 25, "ANZ": 25, "APAC": 15}

RISK_TIERS = ("low", "medium", "high", "critical")
QUALITY_FLAGS = (0, 1, 2)


@dataclass(frozen=True)
class Generated:
    """Bundled output of a generator run."""
    assets:        list[dict]
    observations:  list[dict]
    risk_scores:   list[dict]


# ---------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------

def _jitter(rng: random.Random, lon: float, lat: float, radius_deg: float = 0.10
            ) -> tuple[float, float]:
    """Random point within ``radius_deg`` of (lon, lat)."""
    r = radius_deg * math.sqrt(rng.random())
    a = rng.random() * 2 * math.pi
    return lon + r * math.cos(a), lat + r * math.sin(a) / 1.6


def _wkt_for_class(rng: random.Random, geom_type: str,
                   anchor_lon: float, anchor_lat: float) -> str:
    """Build a WGS84 WKT string suitable for the given asset class."""
    if geom_type == "Point":
        x, y = _jitter(rng, anchor_lon, anchor_lat)
        return f"SRID=4326;POINT({x:.6f} {y:.6f})"

    if geom_type == "LineString":
        x, y = _jitter(rng, anchor_lon, anchor_lat, 0.06)
        bearing = rng.random() * 2 * math.pi
        pts = [(x, y)]
        for _ in range(3):
            bearing += rng.uniform(-0.7, 0.7)
            step = rng.uniform(0.005, 0.015)
            x += math.cos(bearing) * step
            y += math.sin(bearing) * step / 1.6
            pts.append((x, y))
        body = ", ".join(f"{px:.6f} {py:.6f}" for px, py in pts)
        return f"SRID=4326;LINESTRING({body})"

    if geom_type == "Polygon":
        cx, cy = _jitter(rng, anchor_lon, anchor_lat, 0.04)
        size = rng.uniform(0.003, 0.010)
        pts = []
        for i in range(6):
            a = i * math.pi / 3
            pts.append((cx + math.cos(a) * size,
                        cy + math.sin(a) * size / 1.6))
        pts.append(pts[0])
        body = ", ".join(f"{px:.6f} {py:.6f}" for px, py in pts)
        return f"SRID=4326;POLYGON(({body}))"

    raise ValueError(f"Unknown geometry type: {geom_type}")


# ---------------------------------------------------------------
# Score / tier helpers
# ---------------------------------------------------------------

def _condition_score(rng: random.Random, install_year: int | None,
                     material: str | None) -> float:
    """Plausibly-biased condition score in [0, 100].

    Older + legacy materials skew lower (poorer condition).
    """
    base = 80.0
    if install_year:
        age = max(0, 2026 - install_year)
        base -= min(40.0, age * 0.45)
    if material in {"Cast Iron", "Vitrified Clay"}:
        base -= 8.0
    elif material in {"HDPE", "Composite"}:
        base += 4.0
    base += rng.uniform(-6.0, 6.0)
    return max(0.0, min(100.0, base))


def _risk_tier_from_score(score: float) -> str:
    """Map a condition score to a tier.

    The thresholds match the convention used by the GeoAI pipeline on
    feat/jisp-mvp (lower condition score -> higher risk tier).
    """
    if score < 30:  return "critical"
    if score < 50:  return "high"
    if score < 70:  return "medium"
    return "low"


# ---------------------------------------------------------------
# Pure generators (testable without a DB)
# ---------------------------------------------------------------

def _weighted_choice(rng: random.Random, weights: dict[str, float]) -> str:
    items = list(weights.items())
    total = sum(w for _, w in items)
    r = rng.random() * total
    cum = 0.0
    for key, w in items:
        cum += w
        if r <= cum:
            return key
    return items[-1][0]


def generate_assets(count: int = 200, seed: int = 42) -> list[dict]:
    """Generate ``count`` realistic synthetic asset rows.

    Returns plain dicts shaped for direct INSERT into the ``assets``
    table from migration 003.
    """
    rng = random.Random(seed)

    # Class lookup: code -> profile tuple
    profiles = {p[0]: p for p in ASSET_CLASS_PROFILES}

    rows: list[dict] = []
    for i in range(count):
        region_code  = _weighted_choice(rng, REGION_WEIGHTS)
        asset_class  = _weighted_choice(rng, DEFAULT_CLASS_WEIGHTS)
        _, geom_type, materials, dia_rng, len_rng, cap_rng, depth_rng = profiles[asset_class]

        anchor_name, anchor_lon, anchor_lat = rng.choice(ANCHORS[region_code])
        wkt = _wkt_for_class(rng, geom_type, anchor_lon, anchor_lat)

        material = rng.choice(materials) if materials else None
        install_year = rng.randint(1925, 2024) if rng.random() < 0.85 else None

        diameter_mm = rng.randint(*dia_rng) if dia_rng[1] > 0 else None
        length_m    = float(rng.randint(*len_rng)) if len_rng[1] > 0 else None
        capacity_ml = round(rng.uniform(*cap_rng), 2) if cap_rng[1] > 0.0 else None
        depth_m     = round(rng.uniform(*depth_rng), 2) if depth_rng[1] > 0.0 else None

        condition_score = round(_condition_score(rng, install_year, material), 1)
        risk_tier       = _risk_tier_from_score(condition_score)

        external_id = f"SEED-{region_code}-{asset_class}-{i:04d}"
        rows.append({
            "external_id":     external_id,
            "region_code":     region_code,
            "asset_class":     asset_class,
            "name":            f"{asset_class} {anchor_name} #{i:04d}",
            "description":     None,
            "owner":           "Sample Water Authority",
            "geometry_wkt":    wkt,
            "material":        material,
            "diameter_mm":     diameter_mm,
            "length_m":        length_m,
            "capacity_ml":     capacity_ml,
            "elevation_m":     None,
            "depth_m":         depth_m,
            "pressure_zone":   None,
            "install_year":    install_year,
            "condition_score": condition_score,
            "risk_tier":       risk_tier,
            "last_inspected":  None,
            "next_inspection": None,
            "is_critical":     rng.random() < 0.10,
            "is_active":       True,
            "attributes":      {"anchor": anchor_name, "criticality_band":
                                rng.choice(["low", "medium", "high"])},
            "source":          "seed",
        })
    return rows


def generate_observations(assets: Sequence[dict], days: int = 30,
                          seed: int = 42) -> list[dict]:
    """Generate a synthetic time series for sensor + meter assets.

    Two metrics per eligible asset (``pressure_psi`` and ``flow_lps``)
    sampled hourly for the most recent ``days`` days.
    """
    rng = random.Random(seed + 1)
    eligible = [a for a in assets if a["asset_class"] in {"SENSOR", "METER"}]
    points: list[dict] = []
    sample_count = days * 24
    for asset in eligible:
        ext_id = asset["external_id"]
        base_pressure = rng.uniform(45, 75)
        base_flow     = rng.uniform(2.0, 12.0)
        for i in range(sample_count):
            seasonal = math.sin(i / 12.0)
            pressure = base_pressure + seasonal * 4 + rng.uniform(-1.5, 1.5)
            flow     = base_flow     + seasonal * 1 + rng.uniform(-0.5, 0.5)
            ts_offset_hours = sample_count - 1 - i
            points.append({
                "external_id": ext_id,
                "metric":      "pressure_psi",
                "value":       round(pressure, 2),
                "unit":        "psi",
                "quality_flag": rng.choices(QUALITY_FLAGS, weights=[92, 7, 1])[0],
                "source":      "seed",
                "ts_offset_hours": ts_offset_hours,
            })
            points.append({
                "external_id": ext_id,
                "metric":      "flow_lps",
                "value":       round(flow, 2),
                "unit":        "L/s",
                "quality_flag": rng.choices(QUALITY_FLAGS, weights=[92, 7, 1])[0],
                "source":      "seed",
                "ts_offset_hours": ts_offset_hours,
            })
    return points


def generate_initial_risk_scores(assets: Sequence[dict], seed: int = 42
                                 ) -> list[dict]:
    """Seed `risk_scores` rows for the higher-risk subset.

    Matches mvp's 0-100 risk_score scale; SHAP values are stubs.
    """
    rng = random.Random(seed + 2)
    out: list[dict] = []
    for a in assets:
        if a["risk_tier"] not in {"high", "critical"} and rng.random() > 0.25:
            continue
        score = max(0.0, min(100.0, 100.0 - a["condition_score"] +
                             rng.uniform(-5, 5)))
        tier = _risk_tier_from_score(100.0 - score)
        out.append({
            "external_id":   a["external_id"],
            "risk_score":    round(score, 2),
            "risk_tier":     tier,
            "model_version": "seed-v1",
            "shap_values":   {"age": round(rng.uniform(-0.3, 0.3), 3),
                              "material": round(rng.uniform(-0.2, 0.2), 3)},
            "features_used": {"install_year": a["install_year"],
                              "material":     a["material"]},
            "anomaly_flag":  rng.random() < 0.15,
            "anomaly_types": [],
            "notes":         "seeded baseline — replace once GeoAI pipeline runs",
        })
    return out


def generate_all(asset_count: int = 200, seed: int = 42,
                 observation_days: int = 30) -> Generated:
    assets = generate_assets(asset_count, seed)
    obs    = generate_observations(assets, observation_days, seed)
    scores = generate_initial_risk_scores(assets, seed)
    return Generated(assets=assets, observations=obs, risk_scores=scores)


# ---------------------------------------------------------------
# DB writer
# ---------------------------------------------------------------

def apply(dsn: str, batch: Generated) -> dict[str, int]:
    """Apply the generated batch to the database. Idempotent.

    Strategy: in a single transaction, delete every ``source='seed'`` row
    from observations + risk_scores + assets (in dependency order), then
    insert the fresh batch.
    """
    try:
        import psycopg  # type: ignore
        from psycopg import sql  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on env
        raise SystemExit(
            "psycopg (v3) is required to apply seed data. "
            "Install with: pip install 'psycopg[binary]>=3.1'"
        ) from exc

    counts = {"assets": 0, "observations": 0, "risk_scores": 0}

    with psycopg.connect(dsn, autocommit=False) as conn:
        with conn.cursor() as cur:
            # Wipe prior seed rows (children first thanks to FKs)
            cur.execute("DELETE FROM observations WHERE source = 'seed'")
            cur.execute("DELETE FROM risk_scores  WHERE asset_id IN "
                        "(SELECT asset_id FROM assets WHERE source = 'seed')")
            cur.execute("DELETE FROM assets       WHERE source = 'seed'")

            # Insert assets and capture asset_id by external_id.
            asset_ids: dict[str, str] = {}
            for a in batch.assets:
                cur.execute(
                    """INSERT INTO assets
                       (external_id, region_code, asset_class, name, description,
                        owner, geometry, material, diameter_mm, length_m,
                        capacity_ml, elevation_m, depth_m, pressure_zone,
                        install_year, condition_score, risk_tier,
                        is_critical, is_active, attributes, source)
                       VALUES
                       (%s, %s, %s, %s, %s,
                        %s, ST_GeomFromEWKT(%s), %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s::jsonb, %s)
                       RETURNING asset_id::text""",
                    (a["external_id"], a["region_code"], a["asset_class"],
                     a["name"], a["description"], a["owner"], a["geometry_wkt"],
                     a["material"], a["diameter_mm"], a["length_m"],
                     a["capacity_ml"], a["elevation_m"], a["depth_m"],
                     a["pressure_zone"], a["install_year"], a["condition_score"],
                     a["risk_tier"], a["is_critical"], a["is_active"],
                     json.dumps(a["attributes"]), a["source"]))
                row = cur.fetchone()
                asset_ids[a["external_id"]] = row[0]
                counts["assets"] += 1

            # Bulk insert observations (mapping external_id -> asset_id).
            obs_rows = [
                (asset_ids[o["external_id"]], o["metric"], o["value"], o["unit"],
                 o["quality_flag"], o["source"], o["ts_offset_hours"])
                for o in batch.observations
                if o["external_id"] in asset_ids
            ]
            if obs_rows:
                cur.executemany(
                    """INSERT INTO observations
                           (asset_id, metric, value, unit, quality_flag, source, time)
                       VALUES
                           (%s::uuid, %s, %s, %s, %s, %s,
                            now() - (%s || ' hours')::interval)""",
                    obs_rows)
                counts["observations"] = len(obs_rows)

            # Insert risk scores (mapping external_id -> asset_id).
            score_rows = [
                (asset_ids[s["external_id"]], s["risk_score"], s["risk_tier"],
                 s["model_version"], json.dumps(s["shap_values"]),
                 json.dumps(s["features_used"]), s["anomaly_flag"],
                 s["anomaly_types"], s["notes"])
                for s in batch.risk_scores
                if s["external_id"] in asset_ids
            ]
            if score_rows:
                cur.executemany(
                    """INSERT INTO risk_scores
                           (asset_id, risk_score, risk_tier, model_version,
                            shap_values, features_used, anomaly_flag,
                            anomaly_types, notes)
                       VALUES
                           (%s::uuid, %s, %s, %s, %s::jsonb, %s::jsonb,
                            %s, %s, %s)""",
                    score_rows)
                counts["risk_scores"] = len(score_rows)

        conn.commit()

    return counts


# ---------------------------------------------------------------
# CLI
# ---------------------------------------------------------------

def _resolve_dsn(cli_dsn: str | None) -> str:
    if cli_dsn:
        return cli_dsn
    env = os.environ.get("JISP_DATABASE_URL")
    if env:
        return env
    raise SystemExit(
        "No database DSN provided. Pass --dsn or set JISP_DATABASE_URL."
    )


def _print_dry_run(batch: Generated) -> None:
    print(f"Generated {len(batch.assets)} assets, "
          f"{len(batch.observations)} observations, "
          f"{len(batch.risk_scores)} risk_scores.\n")
    print("Assets per region:")
    by_region: dict[str, int] = {}
    for a in batch.assets:
        by_region[a["region_code"]] = by_region.get(a["region_code"], 0) + 1
    for code, n in sorted(by_region.items()):
        print(f"  {code:<6} {n}")
    print("\nAssets per class:")
    by_class: dict[str, int] = {}
    for a in batch.assets:
        by_class[a["asset_class"]] = by_class.get(a["asset_class"], 0) + 1
    for code, n in sorted(by_class.items(), key=lambda kv: -kv[1]):
        print(f"  {code:<10} {n}")
    print("\nFirst 3 assets (truncated):")
    for a in batch.assets[:3]:
        wkt_short = a["geometry_wkt"][:40] + "…"
        print(f"  {a['external_id']}  {a['name']}  "
              f"score={a['condition_score']}  tier={a['risk_tier']}  "
              f"geom={wkt_short}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed JISP with sample data.")
    parser.add_argument("--dsn", help="PostgreSQL DSN. Defaults to $JISP_DATABASE_URL.")
    parser.add_argument("--count", type=int, default=200,
                        help="Number of assets to generate (default 200).")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducibility (default 42).")
    parser.add_argument("--observation-days", type=int, default=30,
                        help="Days of synthetic observations (default 30).")
    parser.add_argument("--no-observations", action="store_true",
                        help="Skip observation generation (faster).")
    parser.add_argument("--no-risk-scores", action="store_true",
                        help="Skip risk_scores seeding.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print a summary; do not connect to the DB.")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    batch = generate_all(
        asset_count=args.count,
        seed=args.seed,
        observation_days=0 if args.no_observations else args.observation_days,
    )
    if args.no_risk_scores:
        batch = Generated(assets=batch.assets, observations=batch.observations,
                          risk_scores=[])

    if args.dry_run:
        _print_dry_run(batch)
        return 0

    dsn = _resolve_dsn(args.dsn)
    counts = apply(dsn, batch)
    print(f"Applied to {dsn.split('@')[-1]}: "
          f"{counts['assets']} assets, "
          f"{counts['observations']} observations, "
          f"{counts['risk_scores']} risk_scores.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
