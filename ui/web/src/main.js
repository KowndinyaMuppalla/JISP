/**
 * @file Bootstrap — wires every component together.
 *
 * Mode selection:
 *   window.JISP_CONFIG = { apiBaseUrl: "...", apiMode: "auto"|"live"|"mock" }
 *   can be set in index.html (above the module script tag) to point the
 *   client at a real backend. Defaults to mock.
 */

import { ApiClient } from "./api/client.js";
import { JispMap, REGION_BOUNDS } from "./map.js";
import { LayerPanel }  from "./panels/layer-panel.js";
import { AssetPanel }  from "./panels/asset-panel.js";
import { ImportPanel } from "./panels/import-panel.js";
import { SearchBox }   from "./panels/search.js";
import { $ } from "./util/dom.js";
import { fmtLonLat } from "./util/format.js";

const cfg = /** @type {{apiBaseUrl?:string,apiMode?:"auto"|"live"|"mock"}} */ (
  /** @type any */ (window).JISP_CONFIG ?? {}
);

async function main() {
  const api = new ApiClient({ baseUrl: cfg.apiBaseUrl, mode: cfg.apiMode ?? "auto" });
  await api.probe();
  _renderApiModeBadge(api.isLive);

  // Asset panel needs to be ready before map clicks fire.
  const assetPanel = new AssetPanel({ apiClient: api });
  assetPanel.mount();

  const layerPanel = new LayerPanel({
    onChange: (state) => {
      jispMap.setFilters(state);
      jispMap.setClusterVisibility(state.clusters);
    },
    onRegionJump: (code) => jispMap.flyToRegion(/** @type any */(code)),
  });
  layerPanel.mount();

  const importPanel = new ImportPanel({ apiClient: api });
  importPanel.mount();

  const search = new SearchBox({
    apiClient: api,
    onPick: (feature) => {
      const center = _featureCentre(feature);
      if (center) jispMap.flyTo(center, 14);
      jispMap.setSelected(feature.properties.id);
      assetPanel.show(feature);
    },
  });
  search.mount();

  const jispMap = new JispMap({
    container: "map",
    apiClient: api,
    onAssetSelect: async (id) => {
      if (!id) { assetPanel.close(); return; }
      const feature = await api.getAsset(id);
      if (feature) assetPanel.show(feature);
    },
    onCameraChange: (bounds) => {
      $("#status-tiles").textContent = api.isLive ? "live · basemap" : "mock · basemap";
    },
  });
  await jispMap.init();

  // Region jump button → cycles regions
  const regions = ["us", "uk", "anz_au", "anz_nz", "apac"];
  const labels = {
    us: "United States", uk: "United Kingdom",
    anz_au: "Australia", anz_nz: "New Zealand", apac: "Asia Pacific",
  };
  let regionIdx = 0;
  $("#region-jump-btn").addEventListener("click", () => {
    regionIdx = (regionIdx + 1) % regions.length;
    const r = regions[regionIdx];
    jispMap.flyToRegion(/** @type any */(r));
    $("#region-jump-label").textContent = labels[r];
    /** @type {HTMLElement} */
    ($("#region-jump-btn").querySelector(".dot")).className =
      `dot dot--${r === "anz_au" || r === "anz_nz" ? "anz" : r}`;
  });

  // Cursor lon/lat in the status bar
  jispMap.map?.on("mousemove", (e) => {
    $("#status-cursor").textContent = fmtLonLat(e.lngLat.lng, e.lngLat.lat);
  });

  // Initial counts for the layer panel
  const initial = await api.listAssets();
  const clusterZones = await api.listClusterZones();
  const counts = _countByCategory(initial.features);
  layerPanel.setCounts({
    regions: counts.regions,
    classes: counts.classes,
    clusters: clusterZones.features.length,
  });
  $("#status-count").textContent = String(initial.features.length);
}

/** @param {boolean} isLive */
function _renderApiModeBadge(isLive) {
  const el = $("#status-mode");
  if (isLive) {
    el.textContent = "LIVE API";
    el.classList.remove("badge--mock");
    el.classList.add("badge--live");
  } else {
    el.textContent = "MOCK API";
  }
}

/** @param {import("./api/types.js").AssetFeature} f */
function _featureCentre(f) {
  switch (f.geometry.type) {
    case "Point":      return /** @type any */ (f.geometry.coordinates);
    case "LineString": {
      const c = f.geometry.coordinates;
      return /** @type any */ (c[Math.floor(c.length / 2)]);
    }
    case "Polygon": {
      const ring = f.geometry.coordinates[0];
      const sx = ring.reduce((a, p) => a + p[0], 0) / ring.length;
      const sy = ring.reduce((a, p) => a + p[1], 0) / ring.length;
      return /** @type any */ ([sx, sy]);
    }
    default: return null;
  }
}

/** @param {import("./api/types.js").AssetFeature[]} features */
function _countByCategory(features) {
  const regions = {}, classes = {};
  for (const f of features) {
    const p = f.properties;
    regions[p.region_code] = (regions[p.region_code] ?? 0) + 1;
    classes[p.class_code]  = (classes[p.class_code]  ?? 0) + 1;
  }
  return { regions, classes };
}

main().catch((err) => {
  console.error("[JISP] bootstrap failed:", err);
  document.body.insertAdjacentHTML("beforeend",
    `<pre style="position:fixed;top:80px;left:30px;right:30px;padding:18px;
       background:#190b0b;color:#ffb4b4;border:1px solid #4d1a1a;border-radius:10px;
       font:12px/1.5 ui-monospace,monospace;z-index:200">${String(err.stack ?? err)}</pre>`);
});

// Sanity touch so the bundler doesn't drop the import.
void REGION_BOUNDS;
