"""Seeded demo data for the JISP Streamlit dashboard.

Responsibility (strict, per ADR 001): UI-layer visualization only. This module
holds fixed, in-memory sample data so the dashboard is demonstrable without a
live database or ingestion pipeline. When the spatial/ingestion layers come
online, this file is the first thing that gets deleted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DemoAsset:
    """A seeded asset shown on the demo map.

    lat/lon use WGS84. `severity_raw` and `proximity_km` are pre-computed to
    look like plausible GeoAI output — the demo never actually runs a detector,
    it hands these values straight to the reasoning layer.
    """

    id: str
    type: str
    name: str
    lat: float
    lon: float
    severity_raw: float
    proximity_km: float
    elevation_m: float
    fema_zone: str
    signals: list[str]


# Chicago-area demo set. Positions picked near the Chicago River / Des Plaines
# floodplain so the map reads as coherent without anyone knowing the geography.
DEMO_ASSETS: list[DemoAsset] = [
    DemoAsset(
        id="PUMP-001",
        type="pump_station",
        name="Riverside Pump Station 1",
        lat=41.8781,
        lon=-87.6298,
        severity_raw=0.78,
        proximity_km=2.5,
        elevation_m=12.0,
        fema_zone="AE (1% annual chance)",
        signals=[
            "Active flood zone detected within 5 km",
            "Asset sits inside FEMA AE floodplain boundary",
            "Nearest river gauge reading at 78th percentile of historical record",
        ],
    ),
    DemoAsset(
        id="BRIDGE-014",
        type="road_bridge",
        name="Des Plaines Crossing",
        lat=41.8901,
        lon=-87.6454,
        severity_raw=0.64,
        proximity_km=3.9,
        elevation_m=18.0,
        fema_zone="X (shaded, 0.2% annual chance)",
        signals=[
            "Bridge within 500 m of observed high-water mark",
            "Upstream discharge at 62nd percentile over 72 h window",
        ],
    ),
    DemoAsset(
        id="SUBSTATION-07",
        type="power_substation",
        name="Lakeshore Substation",
        lat=41.8662,
        lon=-87.6138,
        severity_raw=0.42,
        proximity_km=6.8,
        elevation_m=22.0,
        fema_zone="X (unshaded)",
        signals=[
            "Substation outside active flood polygon",
            "Access road intersects AE zone 1.2 km south",
        ],
    ),
    DemoAsset(
        id="TELECOM-22",
        type="comms_tower",
        name="North Branch Relay",
        lat=41.9109,
        lon=-87.6510,
        severity_raw=0.55,
        proximity_km=4.2,
        elevation_m=15.5,
        fema_zone="AE (1% annual chance)",
        signals=[
            "Tower base elevation 2 m above last recorded flood crest",
            "Access road submerged in 2023 event",
        ],
    ),
    DemoAsset(
        id="PUMP-019",
        type="pump_station",
        name="Riverside Pump Station 2",
        lat=41.8592,
        lon=-87.6420,
        severity_raw=0.88,
        proximity_km=1.1,
        elevation_m=9.0,
        fema_zone="AE (1% annual chance)",
        signals=[
            "Active flood zone directly adjacent (0 m buffer)",
            "Prior inundation at this location in 2020 and 2023",
            "Rainfall over prior 72 h at 91st percentile",
        ],
    ),
]


# Rough representative flood polygon around the Chicago River corridor. This is
# illustrative — not a real FEMA layer. Kept coarse so MapLibre/folium renders
# it cleanly at demo zoom levels.
DEMO_FLOOD_ZONE_GEOJSON: dict[str, Any] = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {
                "zone_id": "FLOOD-ZONE-CHICAGO-01",
                "label": "Active flood zone (demo)",
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-87.6620, 41.8550],
                        [-87.6380, 41.8550],
                        [-87.6220, 41.8720],
                        [-87.6300, 41.8950],
                        [-87.6500, 41.9120],
                        [-87.6680, 41.8900],
                        [-87.6720, 41.8700],
                        [-87.6620, 41.8550],
                    ]
                ],
            },
        }
    ],
}


def get_asset(asset_id: str) -> DemoAsset | None:
    """Lookup helper used by the dashboard."""
    return next((a for a in DEMO_ASSETS if a.id == asset_id), None)


def build_explain_context(asset: DemoAsset) -> dict[str, Any]:
    """Construct the `context` payload for POST /explain.

    Matches the `flood_proximity` shape from api/schemas/payloads.py so the
    reasoning layer can interpolate it against the asset_risk template.
    """
    return {
        "finding_type": "flood_proximity",
        "asset_id": asset.id,
        "asset_type": asset.type,
        "severity_raw": {
            "value": asset.severity_raw,
            "unit_description": (
                "normalized proximity-and-exposure measure, 0 baseline to 1 maximum"
            ),
        },
        "metrics": {
            "proximity_km": asset.proximity_km,
            "elevation_m": asset.elevation_m,
            "fema_zone": asset.fema_zone,
        },
        "signals": list(asset.signals),
        "geometry_reference": {
            "format": "wkt",
            "value": f"POINT({asset.lon} {asset.lat})",
        },
    }
