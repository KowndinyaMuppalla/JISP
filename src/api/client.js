/**
 * @file Single API surface used by every panel.
 *
 * Mode:
 *   - `mock`  : Calls in-memory mocks (./mocks.js).
 *   - `live`  : Calls real fetch endpoints under config.baseUrl.
 *   - `auto`  : Probes the data endpoint once; on success uses live,
 *               otherwise falls back to mocks. Only goes live if the
 *               response shape matches what the frontend expects.
 *
 * To plug the real backend in:
 *   1. Set window.JISP_CONFIG.apiBaseUrl = "http://localhost:8000".
 *   2. Set window.JISP_CONFIG.apiMode = "live" (or leave "auto").
 *
 * Every method below has a TODO marker pointing to the real route so
 * a backend dev can grep "TODO(api)" and implement them in order.
 */

import "./types.js";
import * as mocks from "./mocks.js";

const DEFAULT_TIMEOUT_MS = 15000;

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

  /**
   * Probe the actual data endpoint (not just /health) so we only go live
   * when the full stack - API + DB - is working and returns the right shape.
   */
  async probe() {
    if (this.mode === "mock") { this._live = false; return; }
    if (this.mode === "live") { this._live = true; return; }
    if (this._probe) return this._probe;
    this._probe = (async () => {
      if (!this.baseUrl) { this._live = false; return; }
      try {
        const ctrl  = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), 3000);
        const res   = await fetch(`${this.baseUrl}/api/v1/assets?limit=1`, { signal: ctrl.signal });
        clearTimeout(timer);
        if (!res.ok) { this._live = false; return; }
        const data = await res.json();
        // Only go live if the response is the GeoJSON FeatureCollection shape the frontend expects.
        this._live = Array.isArray(data?.features);
      } catch {
        this._live = false;
      }
    })();
    return this._probe;
  }

  // ---------- internal fetch helper ----------
  async _fetch(path, init) {
    const ctrl  = new AbortController();
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
   * TODO(api): GET ${baseUrl}/api/v1/assets?regions=&classes=&bbox=&high_risk_only=
   * @param {import("./types.js").ListAssetsFilters} [filters]
   * @returns {Promise<import("./types.js").AssetCollection>}
   */
  async listAssets(filters = {}) {
    if (!this._live) return mocks.mockListAssets(filters);
    try {
      const qs = new URLSearchParams();
      filters.regions?.forEach((r) => qs.append("regions", r));
      filters.classes?.forEach((c) => qs.append("classes", c));
      if (filters.bbox)         qs.set("bbox", filters.bbox.join(","));
      if (filters.highRiskOnly) qs.set("high_risk_only", "true");
      if (filters.limit)        qs.set("limit", String(filters.limit));
      return await this._fetch(`/api/v1/assets?${qs.toString()}`);
    } catch (err) {
      console.warn("[JISP] listAssets live failed, falling back to mock:", err);
      return mocks.mockListAssets(filters);
    }
  }

  /**
   * Fetch a single asset.
   * TODO(api): GET ${baseUrl}/api/v1/assets/{id}
   * @param {string} id
   * @returns {Promise<import("./types.js").AssetFeature|null>}
   */
  async getAsset(id) {
    if (!this._live) return mocks.mockGetAsset(id);
    try {
      return await this._fetch(`/api/v1/assets/${encodeURIComponent(id)}`);
    } catch (err) {
      console.warn("[JISP] getAsset live failed, falling back to mock:", err);
      return mocks.mockGetAsset(id);
    }
  }

  /**
   * Latest cluster zones.
   * TODO(api): GET ${baseUrl}/api/v1/cluster-zones?active=true
   * @returns {Promise<import("./types.js").ClusterZoneCollection>}
   */
  async listClusterZones() {
    if (!this._live) return mocks.mockListClusterZones();
    try {
      return await this._fetch(`/api/v1/cluster-zones?active=true`);
    } catch (err) {
      console.warn("[JISP] listClusterZones live failed, falling back to mock:", err);
      return mocks.mockListClusterZones();
    }
  }

  /**
   * Search assets.
   * TODO(api): GET ${baseUrl}/api/v1/assets/search?q=
   * @param {string} q
   * @returns {Promise<import("./types.js").AssetFeature[]>}
   */
  async searchAssets(q) {
    if (!this._live) return mocks.mockSearchAssets(q);
    try {
      return await this._fetch(`/api/v1/assets/search?q=${encodeURIComponent(q)}`);
    } catch (err) {
      console.warn("[JISP] searchAssets live failed, falling back to mock:", err);
      return mocks.mockSearchAssets(q);
    }
  }

  /**
   * Generate an explanation for an asset / finding.
   * TODO(api): POST ${baseUrl}/explain  (see api/routes/reasoning.py)
   * @param {import("./types.js").ExplainRequest} req
   * @returns {Promise<import("./types.js").ExplainResponse>}
   */
  async explain(req) {
    if (!this._live) return mocks.mockExplain(req);
    try {
      return await this._fetch(`/explain`, {
        method:  "POST",
        headers: { "content-type": "application/json" },
        body:    JSON.stringify(req),
      });
    } catch (err) {
      console.warn("[JISP] explain live failed, falling back to mock:", err);
      return mocks.mockExplain(req);
    }
  }

  /**
   * Upload a file (zip / shp / gpkg / geojson).
   * TODO(api): POST ${baseUrl}/api/v1/import/upload (multipart/form-data)
   * @param {File} file
   * @returns {Promise<import("./types.js").UploadResponse>}
   */
  async upload(file) {
    if (!this._live) return mocks.mockUpload(file);
    try {
      const fd = new FormData();
      fd.append("file", file);
      return await this._fetch(`/api/v1/import/upload`, { method: "POST", body: fd });
    } catch (err) {
      console.warn("[JISP] upload live failed, falling back to mock:", err);
      return mocks.mockUpload(file);
    }
  }

  /**
   * Time-series observations for an asset.
   * TODO(api): GET ${baseUrl}/api/v1/assets/{id}/observations?metric=&from=&to=
   * @param {string} id
   * @param {{metric?: string, from?: string, to?: string}} [opts]
   */
  async observations(id, opts = {}) {
    if (!this._live) return mocks.mockObservations(id, opts);
    try {
      const qs = new URLSearchParams();
      if (opts.metric) qs.set("metric", opts.metric);
      if (opts.from)   qs.set("from", opts.from);
      if (opts.to)     qs.set("to", opts.to);
      return await this._fetch(`/api/v1/assets/${encodeURIComponent(id)}/observations?${qs.toString()}`);
    } catch (err) {
      console.warn("[JISP] observations live failed, falling back to mock:", err);
      return mocks.mockObservations(id, opts);
    }
  }

  /**
   * Subscribe to a real-time observation stream over WebSocket.
   * TODO(api): WS  ${baseUrl}/ws/assets/{id}/stream
   * @param {string} id
   * @param {(point: import("./types.js").ObservationPoint) => void} onPoint
   * @returns {() => void} unsubscribe
   */
  subscribeStream(id, onPoint) {
    if (!this._live) {
      const t = setInterval(() => {
        onPoint({
          time:  new Date().toISOString(),
          value: +(60 + Math.random() * 12).toFixed(2),
          unit:  "psi",
        });
      }, 4000);
      return () => clearInterval(t);
    }
    const wsBase = this.baseUrl.replace(/^http/, "ws");
    const ws = new WebSocket(`${wsBase}/ws/assets/${encodeURIComponent(id)}/stream`);
    ws.onmessage = (ev) => {
      try { onPoint(JSON.parse(ev.data)); } catch { /* ignore */ }
    };
    return () => ws.close();
  }
}