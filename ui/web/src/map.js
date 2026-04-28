/**
 * @file MapLibre GL setup, layer rendering, click + hover handling.
 *
 * Sources:
 *   "assets"        — point + line + polygon assets (single GeoJSON source).
 *   "cluster-zones" — HDBSCAN polygons (separate source for distinct paint).
 *
 * Layers (drawn bottom→top):
 *   cluster-zones-fill, cluster-zones-line,
 *   asset-polygon-fill, asset-polygon-outline,
 *   asset-line, asset-line-casing,
 *   asset-point, asset-point-halo, asset-point-selected
 *
 * Region focus:
 *   `flyToRegion(code)` jumps to a per-region bounding box (mirrors
 *   the regions table in spatial/db/migrations/002_reference_tables.sql).
 */

import "./api/types.js";

/**
 * Wait for window.maplibregl to be defined.
 * MapLibre is loaded via a synchronous <script> tag in index.html,
 * so this almost always resolves on the first tick. We poll briefly
 * to handle the rare case where the network is still pulling the bundle.
 */
function loadMaplibre() {
  return new Promise((resolve, reject) => {
    const start = performance.now();
    const tick = () => {
      const ml = /** @type any */ (globalThis).maplibregl;
      if (ml) return resolve(ml);
      if (performance.now() - start > 8000) {
        return reject(new Error(
          "MapLibre GL JS failed to load. Check the network tab for " +
          "https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js — " +
          "your network may be blocking unpkg.com."
        ));
      }
      setTimeout(tick, 50);
    };
    tick();
  });
}

/**
 * Light raster basemap (CARTO Positron via raster tiles).
 * Matches the Streamlit-style light UI theme. Inlined as a JSON style so
 * we don't depend on a separate style.json fetch — raster image tiles are
 * CORS-friendlier than vector style fetches and survive most corporate
 * proxies.
 *
 * If tiles are blocked, the white background layer still renders and the
 * asset overlays remain visible — only the basemap imagery is missing.
 */
const BASEMAP_STYLE = {
  version: 8,
  glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
  sources: {
    "carto-light": {
      type: "raster",
      tiles: [
        "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        "https://b.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        "https://c.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        "https://d.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
      ],
      tileSize: 256,
      maxzoom: 19,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OSM</a>' +
        ' &copy; <a href="https://carto.com/attributions" target="_blank" rel="noopener">CARTO</a>',
    },
  },
  layers: [
    {
      id: "background",
      type: "background",
      paint: { "background-color": "#FFFFFF" },
    },
    {
      id: "carto-light",
      type: "raster",
      source: "carto-light",
      paint: { "raster-opacity": 1.0 },
    },
  ],
};

/** Per-region camera presets (bbox in WGS84). */
export const REGION_BOUNDS = {
  us:     [[-125, 24], [-66, 49.5]],
  uk:     [[ -8.7, 49.8], [ 1.8, 60.9]],
  anz_au: [[ 112, -44], [154,  -9]],
  anz_nz: [[ 165.5, -47.5], [179, -33.5]],
  apac:   [[  90, -11], [150, 40]],
};

const RISK_COLOR_EXPR = [
  "interpolate", ["linear"], ["coalesce", ["get", "risk_score"], 0],
  0.0, "#2ec27e",
  0.4, "#e6c84a",
  0.6, "#f08a3c",
  0.8, "#e64545",
];

const SELECTED_COLOR = "#FF4B4B";


export class JispMap {
  /**
   * @param {{
   *   container: string,
   *   apiClient: import("./api/client.js").ApiClient,
   *   onAssetSelect: (id: string|null) => void,
   *   onCameraChange?: (bounds: number[][]) => void,
   * }} opts
   */
  constructor(opts) {
    this.opts = opts;
    /** @type {import("maplibre-gl").Map|null} */ this.map = null;
    /** @type {string|null} */ this._selectedId = null;
    /** @type {import("maplibre-gl").Popup|null} */ this._popup = null;
    this._maplibre = null;
  }

  async init() {
    const hint = document.getElementById("map-loading-hint");
    const setHint = (msg) => { if (hint) hint.textContent = msg; };

    setHint("waiting for MapLibre…");
    const maplibregl = await loadMaplibre();
    this._maplibre = maplibregl;

    const container = document.getElementById(this.opts.container);
    if (!container) throw new Error(`Map container #${this.opts.container} not found`);
    const rect = container.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) {
      // Bail loudly — otherwise MapLibre renders nothing silently.
      throw new Error(
        `Map container #${this.opts.container} has zero size (${rect.width}×${rect.height}). ` +
        "Check styles/layout.css — #map should be position:fixed; inset:0."
      );
    }

    setHint("creating map…");
    this.map = new maplibregl.Map({
      container: this.opts.container,
      style: BASEMAP_STYLE,
      center: [-30, 30],
      zoom: 1.5,
      attributionControl: { compact: true },
      cooperativeGestures: false,
      pitchWithRotate: false,
      dragRotate: false,
      hash: false,
    });

    this.map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    this.map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");

    // Surface tile errors instead of failing silently.
    this.map.on("error", (e) => {
      // Tile load errors are expected if the user is offline; downgrade to console.
      console.warn("[JISP map]", e?.error ?? e);
    });

    this.map.on("load", () => {
      const overlay = document.getElementById("map-loading");
      if (overlay) overlay.remove();
      this._onLoad();
    });

    this.map.on("moveend", () => {
      if (!this.opts.onCameraChange || !this.map) return;
      const b = this.map.getBounds();
      this.opts.onCameraChange([
        [b.getWest(), b.getSouth()],
        [b.getEast(), b.getNorth()],
      ]);
    });
  }

  async _onLoad() {
    if (!this.map) return;
    const m = this.map;

    const [assets, zones] = await Promise.all([
      this.opts.apiClient.listAssets(),
      this.opts.apiClient.listClusterZones(),
    ]);

    m.addSource("assets",        { type: "geojson", data: assets, promoteId: "id" });
    m.addSource("cluster-zones", { type: "geojson", data: zones,  promoteId: "id" });

    // ---- Cluster zones (lowest layer) — Streamlit red ----
    m.addLayer({
      id: "cluster-zones-fill",
      type: "fill",
      source: "cluster-zones",
      paint: {
        "fill-color":   "#FF4B4B",
        "fill-opacity": 0.12,
      },
    });
    m.addLayer({
      id: "cluster-zones-line",
      type: "line",
      source: "cluster-zones",
      paint: {
        "line-color":     "#FF4B4B",
        "line-opacity":   0.65,
        "line-width":     1.6,
        "line-dasharray": [3, 2],
      },
    });

    // ---- Polygon assets ----
    m.addLayer({
      id: "asset-polygon-fill",
      type: "fill",
      source: "assets",
      filter: ["in", "$type", "Polygon"],
      paint: {
        "fill-color":   RISK_COLOR_EXPR,
        "fill-opacity": 0.35,
      },
    });
    m.addLayer({
      id: "asset-polygon-outline",
      type: "line",
      source: "assets",
      filter: ["in", "$type", "Polygon"],
      paint: {
        "line-color":   RISK_COLOR_EXPR,
        "line-width":   1.2,
        "line-opacity": 0.85,
      },
    });

    // ---- Linestring assets (pipes) ----
    m.addLayer({
      id: "asset-line-casing",
      type: "line",
      source: "assets",
      filter: ["in", "$type", "LineString"],
      paint: {
        "line-color":   "#FFFFFF",
        "line-width":   ["interpolate", ["linear"], ["zoom"], 4, 2.0, 12, 7.0],
        "line-opacity": 0.95,
      },
    });
    m.addLayer({
      id: "asset-line",
      type: "line",
      source: "assets",
      filter: ["in", "$type", "LineString"],
      paint: {
        "line-color":   RISK_COLOR_EXPR,
        "line-width":   ["interpolate", ["linear"], ["zoom"], 4, 0.8, 12, 3.5],
        "line-opacity": 0.95,
      },
    });

    // ---- Point assets ----
    m.addLayer({
      id: "asset-point-halo",
      type: "circle",
      source: "assets",
      filter: ["in", "$type", "Point"],
      paint: {
        "circle-color": "#000",
        "circle-opacity": 0.4,
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 4, 12, 12],
        "circle-blur": 0.5,
      },
    });
    m.addLayer({
      id: "asset-point",
      type: "circle",
      source: "assets",
      filter: ["in", "$type", "Point"],
      paint: {
        "circle-color":         RISK_COLOR_EXPR,
        "circle-radius":        ["interpolate", ["linear"], ["zoom"], 3, 3, 12, 7],
        "circle-stroke-color":  "#FFFFFF",
        "circle-stroke-width":  1.2,
      },
    });

    // ---- Selection layer (drawn last) ----
    m.addLayer({
      id: "asset-point-selected",
      type: "circle",
      source: "assets",
      filter: ["all", ["in", "$type", "Point"], ["==", ["id"], ""]],
      paint: {
        "circle-color":        SELECTED_COLOR,
        "circle-radius":       12,
        "circle-stroke-color": "#fff",
        "circle-stroke-width": 2,
      },
    });
    m.addLayer({
      id: "asset-line-selected",
      type: "line",
      source: "assets",
      filter: ["all", ["in", "$type", "LineString"], ["==", ["id"], ""]],
      paint: {
        "line-color": SELECTED_COLOR,
        "line-width": 6,
        "line-opacity": 0.9,
      },
    });

    // ---- Interactions ----
    const clickable = ["asset-point", "asset-line", "asset-polygon-fill"];
    m.on("click", (e) => {
      const hit = m.queryRenderedFeatures(e.point, { layers: clickable })[0];
      this.setSelected(hit ? String(hit.id ?? hit.properties?.id) : null);
      this.opts.onAssetSelect(hit ? String(hit.id ?? hit.properties?.id) : null);
    });

    for (const layer of clickable) {
      m.on("mouseenter", layer, (e) => {
        m.getCanvas().style.cursor = "pointer";
        const f = e.features?.[0]; if (!f) return;
        this._showHoverPopup(e.lngLat, f.properties);
      });
      m.on("mouseleave", layer, () => {
        m.getCanvas().style.cursor = "";
        this._hideHoverPopup();
      });
    }

    // Default camera
    this.flyToRegion("us");
  }

  /** @param {{lng:number,lat:number}} lngLat @param {Record<string,any>} props */
  _showHoverPopup(lngLat, props) {
    if (!this.map || !this._maplibre) return;
    const score = Number(props.risk_score ?? 0);
    const dotColor = score > 0.8 ? "#e64545" : score > 0.6 ? "#f08a3c"
                   : score > 0.4 ? "#e6c84a" : "#2ec27e";
    const html = `
      <div class="jisp-popup__name">${props.name ?? props.asset_code ?? "—"}</div>
      <div class="jisp-popup__meta">${props.class_name ?? ""} · ${props.region_name ?? ""}</div>
      <div class="jisp-popup__risk">
        <span class="jisp-popup__risk-dot" style="background:${dotColor}"></span>
        risk ${score.toFixed(2)} (${props.risk_condition_class ?? "—"})
      </div>`;
    if (!this._popup) {
      this._popup = new this._maplibre.Popup({
        closeButton: false, closeOnClick: false, offset: 14, className: "jisp-popup",
      });
    }
    this._popup.setLngLat(lngLat).setHTML(html).addTo(this.map);
  }

  _hideHoverPopup() { if (this._popup) this._popup.remove(); }

  /** Highlight an asset in the map. @param {string|null} id */
  setSelected(id) {
    this._selectedId = id;
    if (!this.map) return;
    const filt = id ? ["==", ["id"], id] : ["==", ["id"], "__none__"];
    this.map.setFilter("asset-point-selected", ["all", ["in", "$type", "Point"], filt]);
    this.map.setFilter("asset-line-selected",  ["all", ["in", "$type", "LineString"], filt]);
  }

  /** Apply region/class filters to all asset layers. */
  setFilters({ regions, classes, highRiskOnly }) {
    if (!this.map) return;
    const conds = [];
    if (regions?.length) conds.push(["in", ["get", "region_code"], ["literal", regions]]);
    if (classes?.length) conds.push(["in", ["get", "class_code"],  ["literal", classes]]);
    if (highRiskOnly)    conds.push([">=", ["coalesce", ["get", "risk_score"], 0], 0.7]);
    const filt = conds.length ? ["all", ...conds] : null;

    const layerIds = [
      "asset-polygon-fill", "asset-polygon-outline",
      "asset-line", "asset-line-casing",
      "asset-point", "asset-point-halo",
    ];
    for (const id of layerIds) {
      const baseType = id.includes("polygon") ? "Polygon"
                    : id.includes("line")    ? "LineString" : "Point";
      const base = ["in", "$type", baseType];
      this.map.setFilter(id, filt ? ["all", base, filt] : base);
    }
  }

  /** Toggle cluster-zones overlay visibility. @param {boolean} visible */
  setClusterVisibility(visible) {
    if (!this.map) return;
    const v = visible ? "visible" : "none";
    this.map.setLayoutProperty("cluster-zones-fill", "visibility", v);
    this.map.setLayoutProperty("cluster-zones-line", "visibility", v);
  }

  /** @param {keyof typeof REGION_BOUNDS} code */
  flyToRegion(code) {
    if (!this.map) return;
    const b = REGION_BOUNDS[code]; if (!b) return;
    this.map.fitBounds(/** @type any */(b), { padding: 60, duration: 800 });
  }

  /** @param {[number, number]} lngLat @param {number} [zoom] */
  flyTo(lngLat, zoom = 13) {
    this.map?.flyTo({ center: lngLat, zoom, duration: 700 });
  }
}
