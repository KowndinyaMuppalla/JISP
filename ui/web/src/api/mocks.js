/**
 * @file Mock implementations of every JISP API endpoint.
 *
 * Every method here is replaced by a real `fetch` call in `client.js`
 * once the back-end is online. The shapes returned here MUST match the
 * Pydantic models in `api/schemas/payloads.py` and the JSDoc types in
 * `./types.js` so swapping is a one-liner.
 *
 * No I/O — pure JS over an in-memory copy of the static GeoJSON files.
 */

import "./types.js";

const ASSETS_URL          = new URL("../data/sample-assets.geojson", import.meta.url);
const CLUSTER_ZONES_URL   = new URL("../data/sample-cluster-zones.geojson", import.meta.url);
const EXPLAIN_TEMPLATES_URL = new URL("../data/sample-explain.json", import.meta.url);

let _assetsCache = /** @type {import("./types.js").AssetCollection|null} */ (null);
let _clusterZonesCache = /** @type {import("./types.js").ClusterZoneCollection|null} */ (null);
let _explainTemplates = /** @type {Object<string,{template:string, drivers:any[]}>|null} */ (null);

async function loadAssets() {
  if (_assetsCache) return _assetsCache;
  const res = await fetch(ASSETS_URL);
  _assetsCache = await res.json();
  return _assetsCache;
}

async function loadClusterZones() {
  if (_clusterZonesCache) return _clusterZonesCache;
  const res = await fetch(CLUSTER_ZONES_URL);
  _clusterZonesCache = await res.json();
  return _clusterZonesCache;
}

async function loadExplainTemplates() {
  if (_explainTemplates) return _explainTemplates;
  const res = await fetch(EXPLAIN_TEMPLATES_URL);
  _explainTemplates = await res.json();
  return _explainTemplates;
}

function bboxIntersects(geom, bbox) {
  if (!bbox) return true;
  const [minX, minY, maxX, maxY] = bbox;
  let coords = [];
  switch (geom.type) {
    case "Point":      coords = [geom.coordinates]; break;
    case "MultiPoint": coords = geom.coordinates;   break;
    case "LineString": coords = geom.coordinates;   break;
    case "MultiLineString":
    case "Polygon":    coords = geom.coordinates.flat(); break;
    case "MultiPolygon": coords = geom.coordinates.flat(2); break;
    default: return true;
  }
  return coords.some(([x, y]) => x >= minX && x <= maxX && y >= minY && y <= maxY);
}

/* -----------------------------------------------------------
 * Endpoint mocks
 * Each function corresponds to one real backend route. Comments above
 * each function name the eventual route + HTTP verb so swap-out is
 * mechanical.
 * --------------------------------------------------------- */

/**
 * GET /api/v1/assets
 * @param {import("./types.js").ListAssetsFilters} [filters]
 * @returns {Promise<import("./types.js").AssetCollection>}
 */
export async function mockListAssets(filters = {}) {
  const all = await loadAssets();
  const features = all.features.filter((feat) => {
    const p = feat.properties;
    if (filters.regions?.length && !filters.regions.includes(p.region_code)) return false;
    if (filters.classes?.length && !filters.classes.includes(p.class_code)) return false;
    if (filters.highRiskOnly && (p.risk_score ?? 0) < 0.7) return false;
    if (!bboxIntersects(feat.geometry, filters.bbox)) return false;
    return true;
  });
  const limited = filters.limit ? features.slice(0, filters.limit) : features;
  return { type: "FeatureCollection", features: limited };
}

/**
 * GET /api/v1/assets/{id}
 * @param {string} id
 * @returns {Promise<import("./types.js").AssetFeature|null>}
 */
export async function mockGetAsset(id) {
  const all = await loadAssets();
  return all.features.find((f) => f.properties.id === id) ?? null;
}

/**
 * GET /api/v1/cluster-zones
 * @returns {Promise<import("./types.js").ClusterZoneCollection>}
 */
export async function mockListClusterZones() {
  return loadClusterZones();
}

/**
 * GET /api/v1/assets/search?q=...
 * Naive substring match over asset_code + name.
 * @param {string} query
 * @returns {Promise<import("./types.js").AssetFeature[]>}
 */
export async function mockSearchAssets(query) {
  if (!query || query.length < 2) return [];
  const q = query.toLowerCase();
  const all = await loadAssets();
  return all.features
    .filter((f) => {
      const p = f.properties;
      return (
        (p.asset_code ?? "").toLowerCase().includes(q) ||
        (p.name ?? "").toLowerCase().includes(q)
      );
    })
    .slice(0, 12);
}

/**
 * POST /api/v1/explain
 * Returns a canned-but-templated explanation per asset class so the UI
 * shows realistic copy. Latency is jittered to mimic LLM response time.
 * @param {import("./types.js").ExplainRequest} req
 * @returns {Promise<import("./types.js").ExplainResponse>}
 */
export async function mockExplain(req) {
  const start = performance.now();
  const templates = await loadExplainTemplates();
  const asset = await mockGetAsset(req.subject);

  // Simulate ~600-1100ms LLM latency.
  await new Promise((r) => setTimeout(r, 600 + Math.random() * 500));

  const t = templates[req.template] ?? templates.asset_condition;
  const replacements = {
    name:        asset?.properties.name ?? "this asset",
    class_name:  asset?.properties.class_name ?? "asset",
    region_name: asset?.properties.region_name ?? "the region",
    risk_score:  (asset?.properties.risk_score ?? 0).toFixed(2),
    condition:   asset?.properties.risk_condition_class ?? "unknown",
    install_year: asset?.properties.install_year ?? "unknown",
    material:    asset?.properties.material_name ?? "unknown material",
  };
  const explanation = t.template.replace(/{(\w+)}/g, (_, k) => String(replacements[k] ?? `{${k}}`));

  const elapsed = Math.round(performance.now() - start);
  return {
    subject: req.subject,
    template: req.template,
    explanation,
    drivers: t.drivers,
    meta: {
      model: "llama3.3 (mock)",
      latency_ms: elapsed,
      tokens_in: 184,
      tokens_out: 96,
      created_at: new Date().toISOString(),
    },
  };
}

/**
 * POST /api/v1/import/upload
 * Pretends to ingest a file. Always succeeds in mock mode.
 * @param {File} file
 * @returns {Promise<import("./types.js").UploadResponse>}
 */
export async function mockUpload(file) {
  await new Promise((r) => setTimeout(r, 400 + Math.random() * 600));
  return {
    upload_id: `mock-${Math.random().toString(36).slice(2, 10)}`,
    filename: file.name,
    bytes: file.size,
    status: "complete",
    feature_count: Math.floor(20 + Math.random() * 200),
    message: "Stub: real ingestion will normalise CRS, upsert assets and refresh GeoServer.",
  };
}

/**
 * GET /api/v1/assets/{id}/observations?from=&to=&metric=
 * Generates a synthetic 90-day time series with daily cadence.
 * @param {string} assetId
 * @param {{ metric?: string, from?: string, to?: string }} [opts]
 * @returns {Promise<import("./types.js").ObservationsResponse>}
 */
export async function mockObservations(assetId, opts = {}) {
  const metric = opts.metric ?? "pressure_psi";
  const points = [];
  const end = opts.to ? new Date(opts.to) : new Date();
  const start = opts.from ? new Date(opts.from) : new Date(end.getTime() - 90 * 86400_000);

  const base = 65;
  const amp  = 8;
  const stride = (end - start) / 200;
  for (let t = start.getTime(); t <= end.getTime(); t += stride) {
    const day = (t - start) / 86400_000;
    const seasonal = amp * Math.sin(day / 7);
    const noise = (Math.random() - 0.5) * 2;
    points.push({
      time: new Date(t).toISOString(),
      value: +(base + seasonal + noise).toFixed(2),
      unit: "psi",
    });
  }
  return { asset_id: assetId, metric, unit: "psi", points };
}
