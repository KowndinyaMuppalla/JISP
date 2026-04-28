"""Deterministic sample-data generator for the JISP frontend mocks.

Runs offline. Re-running with the same seed produces identical files,
so the generated GeoJSON is committed to the repo and the front-end
can load it via plain `fetch`.

Usage
-----
    python ui/web/src/data/_generate_sample_data.py

Outputs (overwritten in place):
    ui/web/src/data/sample-assets.geojson
    ui/web/src/data/sample-cluster-zones.geojson
    ui/web/src/data/sample-explain.json

Locked decisions:
    - All geometries WGS84 (EPSG:4326).
    - Asset codes follow {REGION}-{CLASS}-{NN} pattern.
    - Risk scores come from a class-weighted distribution biased towards
      legacy materials so the dashboard has visible high-risk clusters.
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

# ---------------------------------------------------------------
# Config
# ---------------------------------------------------------------
SEED = 19_730_412
random.seed(SEED)

OUT_DIR = Path(__file__).parent

REGIONS = {
    "us":     {"name": "United States",  "tz": "America/New_York"},
    "uk":     {"name": "United Kingdom", "tz": "Europe/London"},
    "anz_au": {"name": "Australia",      "tz": "Australia/Sydney"},
    "anz_nz": {"name": "New Zealand",    "tz": "Pacific/Auckland"},
    "apac":   {"name": "Asia Pacific",   "tz": "Asia/Singapore"},
}

CLASSES = {
    "water_pipe":            {"name": "Water main / pipe",        "geom": "linestring"},
    "water_treatment_plant": {"name": "Water treatment plant",    "geom": "point"},
    "pump_station":          {"name": "Pump station",             "geom": "point"},
    "reservoir":             {"name": "Service reservoir",        "geom": "polygon"},
    "valve":                 {"name": "Valve",                    "geom": "point"},
    "hydrant":               {"name": "Fire hydrant",             "geom": "point"},
    "sensor":                {"name": "In-network sensor",        "geom": "point"},
    "dam":                   {"name": "Dam",                      "geom": "point"},
}

MATERIALS = {
    "di":   ("Ductile iron",                "metallic", 100),
    "ci":   ("Cast iron",                   "metallic",  80),
    "steel":("Steel",                       "metallic",  75),
    "pvc":  ("Polyvinyl chloride",          "plastic",   70),
    "hdpe": ("High-density polyethylene",   "plastic",  100),
    "ac":   ("Asbestos cement",             "composite", 50),
    "conc": ("Concrete",                    "composite", 80),
}

# Hand-picked anchors per region — small, well-known cities so the demo
# looks plausible without claiming any specific operator's network.
ANCHORS = {
    "us":     [("Boston", -71.057, 42.358), ("Chicago", -87.629, 41.878), ("Denver", -104.99, 39.74)],
    "uk":     [("London",  -0.128, 51.508), ("Manchester", -2.244, 53.483)],
    "anz_au": [("Sydney", 151.209, -33.868), ("Melbourne", 144.963, -37.814)],
    "anz_nz": [("Auckland", 174.763, -36.848), ("Wellington", 174.776, -41.286)],
    "apac":   [("Singapore", 103.819, 1.352)],
}


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------
def jitter(lon: float, lat: float, deg: float = 0.06) -> tuple[float, float]:
    return (
        lon + random.uniform(-deg, deg),
        lat + random.uniform(-deg / 1.8, deg / 1.8),
    )


def linestring(lon: float, lat: float, length_deg: float = 0.012) -> list[list[float]]:
    """A wiggly 4-point polyline starting near (lon,lat)."""
    bearing = random.uniform(0, 2 * math.pi)
    pts = [(lon, lat)]
    for _ in range(3):
        bearing += random.uniform(-0.6, 0.6)
        step = length_deg * random.uniform(0.6, 1.2)
        lon += math.cos(bearing) * step
        lat += math.sin(bearing) * step
        pts.append((lon, lat))
    return [list(p) for p in pts]


def polygon(lon: float, lat: float, size_deg: float = 0.004) -> list[list[list[float]]]:
    """Rough hexagon centred on (lon,lat)."""
    ring = []
    for i in range(6):
        a = i * math.pi / 3
        ring.append([lon + math.cos(a) * size_deg, lat + math.sin(a) * size_deg])
    ring.append(ring[0])
    return [ring]


def condition_class(score: float) -> str:
    if score < 0.20: return "excellent"
    if score < 0.40: return "good"
    if score < 0.60: return "fair"
    if score < 0.80: return "poor"
    return "critical"


def risk_for(class_code: str, material: str | None, install_year: int | None) -> float:
    """Plausibly biased risk score in [0,1].

    Older legacy materials and earlier install years skew higher.
    """
    base = {
        "water_pipe": 0.35,
        "water_treatment_plant": 0.20,
        "pump_station": 0.30,
        "reservoir": 0.25,
        "valve": 0.40,
        "hydrant": 0.30,
        "sensor": 0.15,
        "dam": 0.55,
    }.get(class_code, 0.30)

    mat_mod = {"ci": 0.20, "ac": 0.25, "steel": 0.05, "di": -0.05,
               "pvc": 0.00, "hdpe": -0.10, "conc": 0.05}.get(material or "", 0.0)

    age_mod = 0.0
    if install_year:
        age = 2026 - install_year
        age_mod = min(0.30, age * 0.005)

    score = base + mat_mod + age_mod + random.uniform(-0.05, 0.05)
    return max(0.0, min(1.0, score))


def geometry_for_class(class_code: str, lon: float, lat: float):
    geom_kind = CLASSES[class_code]["geom"]
    if geom_kind == "point":
        return {"type": "Point", "coordinates": list(jitter(lon, lat))}
    if geom_kind == "linestring":
        ax, ay = jitter(lon, lat, 0.04)
        return {"type": "LineString", "coordinates": linestring(ax, ay)}
    if geom_kind == "polygon":
        ax, ay = jitter(lon, lat, 0.04)
        return {"type": "Polygon", "coordinates": polygon(ax, ay)}
    raise ValueError(class_code)


# ---------------------------------------------------------------
# Asset generation plan per region
# ---------------------------------------------------------------
PLAN = {
    "us":     {"water_pipe": 12, "water_treatment_plant": 2, "pump_station": 3,
               "reservoir": 2, "valve": 5, "hydrant": 4, "sensor": 4, "dam": 1},
    "uk":     {"water_pipe":  9, "water_treatment_plant": 1, "pump_station": 2,
               "reservoir": 2, "valve": 4, "hydrant": 2, "sensor": 3},
    "anz_au": {"water_pipe":  8, "water_treatment_plant": 1, "pump_station": 2,
               "reservoir": 2, "valve": 3, "sensor": 3, "dam": 1},
    "anz_nz": {"water_pipe":  6, "water_treatment_plant": 1, "pump_station": 2,
               "reservoir": 1, "sensor": 2},
    "apac":   {"water_pipe":  4, "water_treatment_plant": 1, "sensor": 2, "valve": 2},
}

PLAUSIBLE_MATERIAL = {
    "water_pipe":            ["di", "ci", "ac", "pvc", "hdpe", "steel"],
    "pump_station":          ["steel", "conc"],
    "reservoir":             ["conc", "steel"],
    "water_treatment_plant": ["conc"],
    "valve":                 ["di", "steel"],
    "hydrant":               ["di"],
    "sensor":                [None],
    "dam":                   ["conc"],
}


def generate_assets() -> list[dict]:
    features: list[dict] = []
    counter: dict[str, int] = {}

    for region_code, plan in PLAN.items():
        anchors = ANCHORS[region_code]
        for class_code, qty in plan.items():
            for _ in range(qty):
                anchor = random.choice(anchors)
                _, lon, lat = anchor
                geom = geometry_for_class(class_code, lon, lat)

                material = random.choice(PLAUSIBLE_MATERIAL.get(class_code, [None]))
                install_year = random.choice(
                    [None] + list(range(1925, 2024))
                ) if random.random() < 0.85 else None
                # Bias older for legacy materials
                if material in {"ci", "ac"} and install_year and install_year > 1980:
                    install_year = random.randint(1925, 1979)

                key = f"{region_code}-{class_code}"
                counter[key] = counter.get(key, 0) + 1
                asset_code = f"{region_code.upper()}-{class_code.upper().replace('_','')[:5]}-{counter[key]:03d}"
                aid = f"jisp-{asset_code.lower()}"

                length_m = None
                if class_code == "water_pipe":
                    length_m = round(random.uniform(120, 1800), 1)
                diameter_mm = None
                if class_code in {"water_pipe", "valve"}:
                    diameter_mm = random.choice([100, 150, 200, 250, 300, 400, 600])

                score = risk_for(class_code, material, install_year)
                cond = condition_class(score)

                feat = {
                    "type": "Feature",
                    "id": aid,
                    "geometry": geom,
                    "properties": {
                        "id": aid,
                        "asset_code": asset_code,
                        "region_code": region_code,
                        "region_name": REGIONS[region_code]["name"],
                        "class_code": class_code,
                        "class_name": CLASSES[class_code]["name"],
                        "material_code": material,
                        "material_name": MATERIALS[material][0] if material else None,
                        "name": f"{CLASSES[class_code]['name']} {asset_code}",
                        "install_year": install_year,
                        "diameter_mm": diameter_mm,
                        "length_m":   length_m,
                        "attributes": {
                            "owner": "Sample Water Authority",
                            "criticality": random.choice(["low","medium","high"]),
                        },
                        "risk_score": round(score, 3),
                        "risk_condition_class": cond,
                        "risk_computed_at": "2026-04-26T08:00:00Z",
                        "source": "mock",
                    },
                }
                features.append(feat)
    return features


def generate_cluster_zones(assets: list[dict]) -> list[dict]:
    """A handful of polygon hotspots over high-risk asset centroids."""
    high = [f for f in assets if f["properties"]["risk_score"] >= 0.6]
    random.shuffle(high)
    zones = []
    used: set[tuple[int, int]] = set()
    cluster_id = 1
    for f in high:
        # Compute centroid
        if f["geometry"]["type"] == "Point":
            lon, lat = f["geometry"]["coordinates"]
        elif f["geometry"]["type"] == "LineString":
            lon, lat = f["geometry"]["coordinates"][0]
        else:
            ring = f["geometry"]["coordinates"][0]
            lon = sum(p[0] for p in ring) / len(ring)
            lat = sum(p[1] for p in ring) / len(ring)

        bucket = (round(lon * 4), round(lat * 4))
        if bucket in used:
            continue
        used.add(bucket)

        ring = polygon(lon, lat, size_deg=0.05)[0]
        zones.append({
            "type": "Feature",
            "id": f"cluster-{cluster_id:02d}",
            "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {
                "id": f"cluster-{cluster_id:02d}",
                "region_code": f["properties"]["region_code"],
                "cluster_id": cluster_id,
                "num_assets": random.randint(4, 12),
                "mean_score": round(random.uniform(0.65, 0.92), 3),
                "computed_at": "2026-04-26T08:00:00Z",
            },
        })
        cluster_id += 1
        if cluster_id > 8:
            break
    return zones


# ---------------------------------------------------------------
# Explanation templates (mock /explain output)
# ---------------------------------------------------------------
EXPLAIN_TEMPLATES = {
    "asset_condition": {
        "template": (
            "{name} in {region_name} currently scores {risk_score} "
            "({condition}). The strongest contributors are its "
            "{install_year} install date and {material} construction. "
            "Observed condition is consistent with peer assets of similar "
            "vintage in this network. Recommended next action: schedule a "
            "condition inspection within the next 90 days; review upstream "
            "pressure trends for the past 30 days. This is a descriptive "
            "explanation of the model's output — not a prediction of failure."
        ),
        "drivers": [
            {"feature": "install_year",   "value": -0.18, "normalized": 0.92},
            {"feature": "material:cast_iron", "value": 0.12, "normalized": 0.62},
            {"feature": "diameter_mm",    "value":  0.06, "normalized": 0.31},
            {"feature": "soil_corrosivity", "value": 0.04, "normalized": 0.21},
            {"feature": "ground_movement",  "value": 0.02, "normalized": 0.10},
        ],
    },
    "flood_proximity": {
        "template": (
            "{name} sits within a 100-year flood envelope. Distance to the "
            "modelled inundation centroid is short enough that a Q100 event "
            "would likely overtop the access road. This is an observational "
            "spatial fact derived from the published flood layer."
        ),
        "drivers": [
            {"feature": "distance_to_floodway_m", "value": -0.22, "normalized": 0.95},
            {"feature": "elevation_m",            "value":  0.08, "normalized": 0.42},
            {"feature": "land_cover:impervious",  "value":  0.05, "normalized": 0.25},
        ],
    },
    "anomaly": {
        "template": (
            "Pressure on {name} dropped 18% over a 24-hour window — outside "
            "the asset's 90-day envelope. Adjacent sensors showed a coincident "
            "rise. Pattern is consistent with a leak event upstream; "
            "inspection of the linked main is suggested."
        ),
        "drivers": [
            {"feature": "z_score_pressure_24h", "value": -0.31, "normalized": 0.99},
            {"feature": "neighbour_correlation", "value":  0.14, "normalized": 0.65},
            {"feature": "diurnal_residual",      "value":  0.07, "normalized": 0.30},
        ],
    },
    "cluster": {
        "template": (
            "{name} sits inside a high-risk hotspot identified by HDBSCAN "
            "over the latest condition surface. The cluster contains "
            "multiple peer assets with similar risk drivers, suggesting a "
            "shared root cause (vintage, material, or environmental)."
        ),
        "drivers": [
            {"feature": "cluster_membership",  "value": 0.24, "normalized": 1.00},
            {"feature": "neighbour_mean_score","value": 0.18, "normalized": 0.78},
            {"feature": "vintage_homogeneity", "value": 0.09, "normalized": 0.36},
        ],
    },
}


# ---------------------------------------------------------------
# Main
# ---------------------------------------------------------------
def main() -> None:
    assets = generate_assets()
    zones  = generate_cluster_zones(assets)

    (OUT_DIR / "sample-assets.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": assets}, indent=2),
        encoding="utf-8",
    )
    (OUT_DIR / "sample-cluster-zones.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": zones}, indent=2),
        encoding="utf-8",
    )
    (OUT_DIR / "sample-explain.json").write_text(
        json.dumps(EXPLAIN_TEMPLATES, indent=2),
        encoding="utf-8",
    )

    print(f"wrote {len(assets)} assets, {len(zones)} cluster zones to {OUT_DIR}")


if __name__ == "__main__":
    main()
