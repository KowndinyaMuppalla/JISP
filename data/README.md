# data/

Local-only data staging area. Contents are not committed (see `.gitignore`).

## Layout

- `raw/` — untouched source data, partitioned by region and provider.
  - `us/usgs/`, `us/epa/`
  - `anz/bom/`, `anz/ea/`
- `processed/` — normalized intermediate artifacts produced by `ingestion/`.
- `reference/` — static reference data.
  - `basemaps/`
  - `administrative-boundaries/`

## Rules

- No secrets, no PII.
- Nothing in `raw/`, `processed/`, or `reference/` is committed.
- Only folder markers (`.gitkeep`) are tracked in git.
