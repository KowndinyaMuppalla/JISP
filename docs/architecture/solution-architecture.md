# JISP Solution Architecture

> Status: placeholder — to be populated in later steps.

## Purpose

JISP is a pre-field, cloud-native, AI-first, geospatial-native, asset-centric,
time-aware, explainable spatial intelligence platform. It runs BEFORE field
execution and provides intelligence, prioritization, and reasoning.

## Component Responsibilities (strict)

| Folder         | Responsibility                                           |
|----------------|----------------------------------------------------------|
| `ingestion/`   | Ingestion & normalization ONLY                           |
| `spatial/`     | PostGIS, assets, geometry ONLY                           |
| `timeseries/`  | TimescaleDB time-series ONLY                             |
| `geoai/`       | Spatial AI & change detection ONLY                       |
| `reasoning/`   | Explanation & reasoning ONLY (Ollama + Kimi)             |
| `api/`         | FastAPI endpoints ONLY                                   |
| `ui/`          | Visualization ONLY                                       |

No cross-folder logic. No offline-first logic in core folders.

## Non-Goals

- Field data capture
- Sync / edge workflows
- Offline-first behavior (core)
