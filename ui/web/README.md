# JISP — Frontend (`ui/web/`)

Streamlit-style MapLibre console for the Jacobs Spatial Intelligence Platform.

Light theme matching Streamlit's default (`primaryColor #FF4B4B`,
`backgroundColor #FFFFFF`, Source Sans Pro). No build step — pure ES
modules + MapLibre GL JS via CDN.

## Running locally

From the repository root:

```bash
cd ui/web
python -m http.server 8080
# then open http://localhost:8080/
```

Any other static server works (`npx serve .`, `caddy file-server`, nginx, etc.).
The page must be served over HTTP — opening `index.html` via `file://`
will fail because of CORS and ES-module rules.

## Mock vs live API

By default the front-end runs against in-memory mocks defined in
`src/api/mocks.js`. To point at a real backend, drop a small inline
config block above the module script tag in `index.html` (or set it
from a server-rendered template):

```html
<script>
  window.JISP_CONFIG = {
    apiBaseUrl: "http://localhost:8000",
    apiMode:    "auto",   // "auto" probes /health; "live" forces; "mock" forces mocks.
  };
</script>
<script type="module" src="./src/main.js"></script>
```

The status-bar badge ("MOCK API" / "LIVE API") reflects the resolved mode.

### Endpoints to implement on the backend

The API client (`src/api/client.js`) has one TODO marker per endpoint —
grep for `TODO(api)` and implement them in this order:

| Endpoint                                              | Purpose                              |
| ----------------------------------------------------- | ------------------------------------ |
| `GET    /health`                                      | Liveness probe (already exists).     |
| `GET    /api/v1/assets`                               | List/filter assets (GeoJSON).        |
| `GET    /api/v1/assets/{id}`                          | Asset detail.                        |
| `GET    /api/v1/assets/search?q=`                     | Top-bar search.                      |
| `GET    /api/v1/cluster-zones?active=true`            | HDBSCAN hotspot polygons.            |
| `POST   /explain`                                     | Reasoning (already partially exists).|
| `POST   /api/v1/import/upload`                        | File upload (zip/gpkg/shp/geojson).  |
| `GET    /api/v1/assets/{id}/observations`             | Time-series readings.                |
| `WS     /ws/assets/{id}/stream`                       | Real-time push.                      |

Schemas the front-end expects are in `src/api/types.js` (JSDoc).
They mirror the Pydantic models in `api/schemas/payloads.py`.

## Layout map

```
+---------------------------------------------------------------+
|  [JISP brand]   [search /]            [region cycle] [Import] |  top bar
+---------------------------------------------------------------+
|                                                                 |
| +-- LAYERS ---+                              +- ASSET DETAIL -+ |
| | Regions     |                              | class · code   | |
| |   ☑ US      |                              | risk score     | |
| |   ☑ UK      |          MAPLIBRE            | attributes     | |
| |   ☑ ANZ     |                              | [Explain]      | |
| |   ☑ APAC    |                              |  → SHAP bars   | |
| | Classes …   |                              +----------------+ |
| | Overlays    |                                                 |
| +-------------+                                                 |
|                                                                 |
+---------------------------------------------------------------+
|  Assets · MOCK API · Tiles · Cursor lon/lat                   |  status bar
+---------------------------------------------------------------+
```

## Sample data

`src/data/sample-assets.geojson` — 97 assets across US/UK/AU/NZ/SG.
`src/data/sample-cluster-zones.geojson` — 8 HDBSCAN hotspot polygons.
`src/data/sample-explain.json` — 4 explanation templates.

Regenerate with:

```bash
python ui/web/src/data/_generate_sample_data.py
```

The generator is deterministic — the same seed always produces the
same files, so the committed JSON is reproducible.

## Source map

```
ui/web/
├── index.html
├── README.md (this file)
└── src/
    ├── main.js                  bootstrap — wires every component
    ├── map.js                   MapLibre setup, layers, interactions
    ├── api/
    │   ├── client.js            ApiClient (mock + live; one fetch per route)
    │   ├── mocks.js             Mock implementations of every endpoint
    │   └── types.js             JSDoc API + GeoJSON types
    ├── panels/
    │   ├── layer-panel.js       Left: region/class toggles + overlays
    │   ├── asset-panel.js       Right: detail + Explain integration
    │   ├── import-panel.js      Drag-and-drop modal
    │   └── search.js            Top-bar asset search
    ├── styles/
    │   ├── tokens.css           Colors, spacing, typography
    │   ├── layout.css           Resets + floating-overlay grid
    │   ├── panels.css           Buttons, toggles, inputs, badges, dropzone
    │   └── map.css              MapLibre control overrides + popup
    └── data/
        ├── _generate_sample_data.py
        ├── sample-assets.geojson
        ├── sample-cluster-zones.geojson
        └── sample-explain.json
```
