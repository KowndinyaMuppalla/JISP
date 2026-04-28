/**
 * @file Single API surface used by every panel.
 *
 * Mode:
 *   - `mock`  : Calls in-memory mocks (./mocks.js).
 *   - `live`  : Calls real fetch endpoints under config.baseUrl.
 *   - `auto`  : Tries `${baseUrl}/health` once at construction; on success
 *               uses live, otherwise falls back to mocks.
 *
 * To plug the real backend in:
 *   1. Set window.JISP_CONFIG.apiBaseUrl = "http://localhost:8000".
 *   2. Set window.JISP_CONFIG.apiMode = "live" (or leave "auto").
 *
 * MVP backend contract (feat/jisp-mvp branch):
 *   GET  /health                              — liveness
 *   GET  /api/v1/assets?region=&asset_class=&risk_tier=&bbox=&limit=&offset=
 *   GET  /api/v1/assets/{asset_id}            — UUID; returns flat row + geojson
 *   GET  /api/v1/assets/{asset_id}/geojson    — geometry-only feature
 *   POST /api/v1/assets                       — create
 *   GET  /api/v1/assets/{asset_id}/observations?metric=&from=&to=
 *   GET  /api/v1/assets/{asset_id}/latest
 *   GET  /api/v1/geoai/inspection-queue?region=&limit=
 *   GET  /api/v1/geoai/explain/{asset_id}     — server-side asset explanation
 *   POST /api/v1/geoai/run                    — kick off pipeline
 *   POST /api/v1/explain                      — generic templated explanation
 *   POST /api/v1/import/upload                — multipart/form-data
 *
 * The MVP returns flat dicts (lon/lat as scalar fields, asset_class as a
 * single value, risk_tier as low/medium/high/critical). The panels and map
 * expect GeoJSON FeatureCollections with the Pydantic-style fields documented
 * in ./types.js. The adapters below normalise mvp shape → frontend shape so
 * the rest of the app stays untouched.
 */

import "./types.js";
import * as mocks from "./mocks.js";

const DEFAULT_TIMEOUT_MS = 15000;

/** mvp risk_tier → frontend risk_condition_class */
const RISK_TIER_TO_CONDITION = {
  low:      "good",
  medium:   "fair",
  high:     "poor",
  critical: "critical",
};

export class ApiClient {
  /**
   * @param {{ baseUrl?: string, mode?: "mock"|"live"|"auto" }} [opts]
   */
  constructor(opts = {}) {
    this.baseUrl = (opts.baseUrl ?? "").replace(/\/$/, "");
    /** @type {"mock"|"live"|"auto"} */
    this.mode    = opts.mode ?? "auto";
    /** Resolved after probe(). */
    this._live   = false;
    /** @type {Promise<void>|null} */
    this._probe  = null;
  }

  /** Whether the client is currently using the live backend. */
  get isLive() { return this._live; }

  /** Force a probe of `${baseUrl}/health`. Idempotent. */
  async probe() {
    if (this.mode === "mock") { this._live = false; return; }
    if (this.mode === "live") {
      this._live = true;
      return;
    }
    if (this._probe) return this._probe;
    this._probe = (async () => {
      if (!this.baseUrl) { this._live = false; return; }
      try {
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), 1500);
        const res = await fetch(`${this.baseUrl}/health`, { signal: ctrl.signal });
        clearTimeout(timer);
        this._live = res.ok;
      } catch {
        this._live = false;
      }
    })();
    return this._probe;
  }

  // ---------- internal fetch helper ----------
  async _fetch(path, init) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), DEFAULT_TIMEOUT_MS);
    try {
      const res = await fetch(`${this.baseUrl}${path}`, { ...init, signal: ctrl.signal });
      if (!res.ok) {
        const text = await res.text().catch(() => "");
        throw new Error(`HTTP ${res.status} ${res.statusText}: ${text}`);
      }
      return await res.json();
    } finally {
      clearTimeout(timer);
    }
  }

  /* =========================================================
   *  Endpoints
   * ========================================================= */

  /**
   * List assets (filtered).
   * Live: GET /api/v1/assets — mvp accepts a single `region` and a single
   * `asset_class`. If the UI has multiple values selected we omit the
   * filter (= no narrowing) rather than firing N requests.
   * @param {import("./types.js").ListAssetsFilters} [filters]
   * @returns {Promise<import("./types.js").AssetCollection>}
   */
  async listAssets(filters = {}) {
    if (!this._live) return mocks.mockListAssets(filters);

    const qs = new URLSearchParams();
    if (filters.regions?.length === 1) qs.set("region",      filters.regions[0]);
    if (filters.classes?.length === 1) qs.set("asset_class", filters.classes[0]);
    if (filters.highRiskOnly)          qs.set("risk_tier",   "high");
    if (filters.bbox)                  qs.set("bbox",        filters.bbox.join(","));
    if (filters.limit)                 qs.set("limit",       String(filters.limit));

    const raw = await this._fetch(`/api/v1/assets?${qs.toString()}`);
    return this._mvpAssetsToCollection(raw);
  }

  /**
   * Fetch a single asset.
   * Live: GET /api/v1/assets/{asset_id} — returns flat row + geojson.
   * @param {string} id
   * @returns {Promise<import("./types.js").AssetFeature|null>}
   */
  async getAsset(id) {
    if (!this._live) return mocks.mockGetAsset(id);
    try {
      const raw = await this._fetch(`/api/v1/assets/${encodeURIComponent(id)}`);
      return this._mvpAssetToFeature(raw);
    } catch (err) {
      if (String(err).includes("HTTP 404")) return null;
      throw err;
    }
  }

  /**
   * Latest cluster zones / hotspots.
   * Live: mvp has no polygon hotspot table yet. Closest analog is the
   * inspection_queue — we surface its rank-1 entries as point features
   * but downstream consumers expect Polygons, so for now we return an
   * empty FeatureCollection in live mode and let the mock keep providing
   * polygons in mock mode.
   * @returns {Promise<import("./types.js").ClusterZoneCollection>}
   */
  async listClusterZones() {
    if (!this._live) return mocks.mockListClusterZones();
    return { type: "FeatureCollection", features: [] };
  }

  /**
   * Search assets.
   * Live: mvp has no /assets/search endpoint, so we filter the standard
   * /assets list client-side. Capped at 12 results to match the dropdown.
   * @param {string} q
   * @returns {Promise<import("./types.js").AssetFeature[]>}
   */
  async searchAssets(q) {
    if (!this._live) return mocks.mockSearchAssets(q);
    if (!q || q.length < 2) return [];
    const collection = await this.listAssets({ limit: 1000 });
    const needle = q.toLowerCase();
    return collection.features
      .filter((f) => {
        const p = f.properties;
        return (
          (p.asset_code ?? "").toLowerCase().includes(needle) ||
          (p.name       ?? "").toLowerCase().includes(needle)
        );
      })
      .slice(0, 12);
  }

  /**
   * Generate a templated explanation.
   * Live: POST /api/v1/explain  (mvp also exposes /api/v1/geoai/explain/{id}
   * but the templated form is the symmetric one).
   * @param {import("./types.js").ExplainRequest} req
   * @returns {Promise<import("./types.js").ExplainResponse>}
   */
  async explain(req) {
    if (!this._live) return mocks.mockExplain(req);
    return this._fetch(`/api/v1/explain`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(req),
    });
  }

  /**
   * Upload a file (zip / shp / gpkg / geojson).
   * Live: POST /api/v1/import/upload — mvp also accepts region_code +
   * asset_class form fields to tag the imported features.
   * @param {File} file
   * @param {{ regionCode?: string, assetClass?: string }} [opts]
   * @returns {Promise<import("./types.js").UploadResponse>}
   */
  async upload(file, opts = {}) {
    if (!this._live) return mocks.mockUpload(file);
    const fd = new FormData();
    fd.append("file", file);
    if (opts.regionCode) fd.append("region_code", opts.regionCode);
    if (opts.assetClass) fd.append("asset_class", opts.assetClass);
    return this._fetch(`/api/v1/import/upload`, { method: "POST", body: fd });
  }

  /**
   * Time-series observations for an asset.
   * Live: GET /api/v1/assets/{asset_id}/observations — mvp returns
   * `{count, observations:[{time, metric, value, unit, ...}]}` (newest first).
   * The panels expect `{points:[{time, value, unit}]}` in chronological order,
   * so the adapter reverses + projects.
   * @param {string} id
   * @param {{metric?: string, from?: string, to?: string}} [opts]
   * @returns {Promise<import("./types.js").ObservationsResponse>}
   */
  async observations(id, opts = {}) {
    if (!this._live) return mocks.mockObservations(id, opts);
    const qs = new URLSearchParams();
    if (opts.metric) qs.set("metric", opts.metric);
    if (opts.from)   qs.set("from",   opts.from);
    if (opts.to)     qs.set("to",     opts.to);
    const raw = await this._fetch(
      `/api/v1/assets/${encodeURIComponent(id)}/observations?${qs.toString()}`
    );
    return this._mvpObservationsToResponse(id, opts.metric ?? "", raw);
  }

  /**
   * Subscribe to a real-time observation stream over WebSocket.
   * mvp does not yet expose /ws/assets/{id}/stream — in live mode we
   * fall back to polling the latest-readings endpoint every 4 s.
   * @param {string} id
   * @param {(point: import("./types.js").ObservationPoint) => void} onPoint
   * @returns {() => void} unsubscribe
   */
  subscribeStream(id, onPoint) {
    if (!this._live) {
      const t = setInterval(() => {
        onPoint({
          time: new Date().toISOString(),
          value: +(60 + Math.random() * 12).toFixed(2),
          unit: "psi",
        });
      }, 4000);
      return () => clearInterval(t);
    }
    let cancelled = false;
    const tick = async () => {
      if (cancelled) return;
      try {
        const data = await this._fetch(
          `/api/v1/assets/${encodeURIComponent(id)}/latest`
        );
        const latest = data?.latest?.[0];
        if (latest) {
          onPoint({ time: latest.time, value: latest.value, unit: latest.unit });
        }
      } catch { /* ignore transient */ }
    };
    tick();
    const interval = setInterval(tick, 4000);
    return () => { cancelled = true; clearInterval(interval); };
  }

  /**
   * Inspection queue (top-N priority assets).
   * Live: GET /api/v1/geoai/inspection-queue
   * @param {{ region?: string, limit?: number }} [opts]
   */
  async inspectionQueue(opts = {}) {
    if (!this._live) {
      // No mock — return an empty payload shaped like the live response.
      return { count: 0, queue: [] };
    }
    const qs = new URLSearchParams();
    if (opts.region) qs.set("region", opts.region);
    if (opts.limit)  qs.set("limit",  String(opts.limit));
    return this._fetch(`/api/v1/geoai/inspection-queue?${qs.toString()}`);
  }

  /* =========================================================
   *  mvp → frontend adapters
   * ========================================================= */

  /**
   * Convert mvp's `{count, assets:[{asset_id, lon, lat, …}]}` into the
   * GeoJSON FeatureCollection the map + panels consume.
   * @param {any} raw
   * @returns {import("./types.js").AssetCollection}
   */
  _mvpAssetsToCollection(raw) {
    if (raw?.type === "FeatureCollection") return raw;       // already shaped
    const rows = raw?.assets ?? [];
    const features = rows
      .map((row) => this._mvpRowToFeature(row))
      .filter(Boolean);
    return { type: "FeatureCollection", features };
  }

  /** @param {any} raw asset detail row from mvp */
  _mvpAssetToFeature(raw) {
    if (!raw) return null;
    if (raw.type === "Feature") return raw;
    // Detail endpoint returns full geojson under .geojson; list endpoint only
    // gives lon/lat — handle both.
    return this._mvpRowToFeature(raw);
  }

  /** @param {any} row */
  _mvpRowToFeature(row) {
    if (!row) return null;
    const id = row.asset_id ?? row.id;
    const geometry = row.geojson ?? (
      row.lon != null && row.lat != null
        ? { type: "Point", coordinates: [Number(row.lon), Number(row.lat)] }
        : null
    );
    if (!geometry) return null;

    const tier = row.risk_tier ?? row.ai_risk_tier ?? null;
    const props = {
      id,
      asset_code:    row.asset_code ?? id,
      region_code:   row.region_code,
      region_name:   row.region_name ?? row.region_code,
      class_code:    row.asset_class ?? row.class_code,
      class_name:    row.asset_class ?? row.class_code,
      material_code: row.material ?? row.material_code ?? null,
      material_name: row.material ?? row.material_name ?? null,
      name:          row.name,
      install_year:  row.install_year ?? null,
      diameter_mm:   row.diameter_mm ?? null,
      length_m:      row.length_m   ?? null,
      attributes:    row.attributes ?? {},
      risk_score:    row.risk_score ?? row.condition_score ?? null,
      risk_condition_class: RISK_TIER_TO_CONDITION[tier] ?? null,
      risk_tier:     tier,
      risk_computed_at: row.scored_at ?? row.last_inspected ?? null,
      source:        row.source ?? "live",
    };
    return { type: "Feature", id, geometry, properties: props };
  }

  /**
   * @param {string} assetId
   * @param {string} metric
   * @param {any} raw  mvp `{count, observations:[{time, metric, value, unit}]}`
   * @returns {import("./types.js").ObservationsResponse}
   */
  _mvpObservationsToResponse(assetId, metric, raw) {
    const rows = raw?.observations ?? [];
    // mvp returns newest-first; the sparkline expects oldest-first.
    const sorted = [...rows].sort(
      (a, b) => new Date(a.time).getTime() - new Date(b.time).getTime()
    );
    const points = sorted.map((r) => ({
      time:  r.time,
      value: Number(r.value),
      unit:  r.unit ?? undefined,
    }));
    const unit = sorted.find((r) => r.unit)?.unit;
    return {
      asset_id: assetId,
      metric:   metric || sorted[0]?.metric || "",
      unit,
      points,
    };
  }
}
