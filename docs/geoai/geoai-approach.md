# JISP GeoAI Approach

> Status: placeholder — to be populated in later steps.

Principles:

- Spatial AI and change detection run in `geoai/` only.
- Models combine spatial features (PySAL, clustering) with temporal
  features (time-series patterns) to produce inspections and risk scores.
- GPU-bound execution is preferred; CPU-only workloads are avoided where
  a GPU is available.
- Every model output must be paired with an explanation artifact (see
  `explainability.md`).
