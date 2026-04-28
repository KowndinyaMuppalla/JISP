# JISP — Frontend (`ui/web/`)

Executive MapLibre console for the **Jacobs Spatial Intelligence
Platform** (JISP).

Jacobs corporate light theme: black wordmark + electric-blue
accent (`#0066FF`), Inter typography, soft layered shadows, live KPI
strip. No build step — pure ES modules + MapLibre GL JS via CDN.

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

### Backend contract — aligned with `feat/jisp-mvp`

The client (`src/api/client.js`) targets the routes shipped on the
`feat/jisp-mvp` branch. Adapter methods inside the client convert the
backend's flat-row responses to the GeoJSON shape the panels consume,
so the rest of the front-end is decoupled from the wire format.

| Endpoint                                                       | Used for                          |
| -------------------------------------------------------------- | --------------------------------- |
| `GET  /health`                                                 | Mode probe.                       |
| `GET  /api/v1/assets?region=&asset_class=&risk_tier=&bbox=`    | Map + KPI strip.                  |
| `GET  /api/v1/assets/{asset_id}`                               | Asset detail panel.               |
| `GET  /api/v1/assets/{asset_id}/observations`                  | 30-day sparkline.                 |
| `GET  /api/v1/assets/{asset_id}/latest`                        | Real-time stream (polled).        |
| `GET  /api/v1/geoai/inspection-queue`                          | Hotspot / queue overlay.          |
| `POST /api/v1/explain`                                         | Right-rail "Generate explanation".|
| `POST /api/v1/import/upload`                                   | Drag-and-drop dropzone.           |

Notes
- mvp accepts a single `region` and a single `asset_class` per request;
  the multi-select layer panel only forwards the filter when exactly
  one value is selected (otherwise the call is unfiltered).
- `risk_tier` (`low`/`medium`/`high`/`critical`) is mapped to the UI's
  `risk_condition_class` (`good`/`fair`/`poor`/`critical`) in the
  client adapter — see `RISK_TIER_TO_CONDITION` in `client.js`.
- mvp has no polygon hotspot table or WebSocket stream yet; the client
  returns an empty FeatureCollection in live mode for cluster zones,
  and falls back to polling `/assets/{id}/latest` for the stream.

Schemas the front-end expects are in `src/api/types.js` (JSDoc).

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
