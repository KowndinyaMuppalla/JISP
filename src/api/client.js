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

  /** Force a probe of `${baseUrl}/health`. Idempotent. */
  async probe() {
    if (this.mode === "mock") { this._live = false; return; }
    if (this.mode === "live") {
      // Trust caller — assume live without probing.
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
   * TODO(api): GET ${baseUrl}/api/v1/assets?regions=&classes=&bbox=&high_risk_only=
   * @param {import("./types.js").ListAssetsFilters} [filters]
   * @returns {Promise<import("./types.js").AssetCollection>}
   */
  async listAssets(filters = {}) {
    if (!this._live) return mocks.mockListAssets(filters);
    const qs = new URLSearchParams();
    filters.regions?.forEach((r) => qs.append("regions", r));
    filters.classes?.forEach((c) => qs.append("classes", c));
    if (filters.bbox)        qs.set("bbox", filters.bbox.join(","));
    if (filters.highRiskOnly) qs.set("high_risk_only", "true");
    if (filters.limit)        qs.set("limit", String(filters.limit));
    return this._fetch(`/api/v1/assets?${qs.toString()}`);
  }

  /**
   * Fetch a single asset.
   * TODO(api): GET ${baseUrl}/api/v1/assets/{id}
   * @param {string} id
   * @returns {Promise<import("./types.js").AssetFeature|null>}
   */
  async getAsset(id) {
    if (!this._live) return mocks.mockGetAsset(id);
    return this._fetch(`/api/v1/assets/${encodeURIComponent(id)}`);
  }

  /**
   * Latest cluster zones.
   * TODO(api): GET ${baseUrl}/api/v1/cluster-zones?active=true
   * @returns {Promise<import("./types.js").ClusterZoneCollection>}
   */
  async listClusterZones() {
    if (!this._live) return mocks.mockListClusterZones();
    return this._fetch(`/api/v1/cluster-zones?active=true`);
  }

  /**
   * Search assets.
   * TODO(api): GET ${baseUrl}/api/v1/assets/search?q=
   * @param {string} q
   * @returns {Promise<import("./types.js").AssetFeature[]>}
   */
  async searchAssets(q) {
    if (!this._live) return mocks.mockSearchAssets(q);
    return this._fetch(`/api/v1/assets/search?q=${encodeURIComponent(q)}`);
  }

  /**
   * Generate an explanation for an asset / finding.
   * TODO(api): POST ${baseUrl}/explain  (see api/routes/reasoning.py)
   * @param {import("./types.js").ExplainRequest} req
   * @returns {Promise<import("./types.js").ExplainResponse>}
   */
  async explain(req) {
    if (!this._live) return mocks.mockExplain(req);
    return this._fetch(`/explain`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(req),
    });
  }

  /**
   * Upload a file (zip / shp / gpkg / geojson).
   * TODO(api): POST ${baseUrl}/api/v1/import/upload (multipart/form-data)
   * @param {File} file
   * @returns {Promise<import("./types.js").UploadResponse>}
   */
  async upload(file) {
    if (!this._live) return mocks.mockUpload(file);
    const fd = new FormData();
    fd.append("file", file);
    return this._fetch(`/api/v1/import/upload`, { method: "POST", body: fd });
  }

  /**
   * Time-series observations for an asset.
   * TODO(api): GET ${baseUrl}/api/v1/assets/{id}/observations?metric=&from=&to=
   * @param {string} id
   * @param {{metric?: string, from?: string, to?: string}} [opts]
   */
  async observations(id, opts = {}) {
    if (!this._live) return mocks.mockObservations(id, opts);
    const qs = new URLSearchParams();
    if (opts.metric) qs.set("metric", opts.metric);
    if (opts.from)   qs.set("from", opts.from);
    if (opts.to)     qs.set("to", opts.to);
    return this._fetch(`/api/v1/assets/${encodeURIComponent(id)}/observations?${qs.toString()}`);
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
      // Mock: emit one synthetic point every 4s.
      const t = setInterval(() => {
        onPoint({
          time: new Date().toISOString(),
          value: +(60 + Math.random() * 12).toFixed(2),
          unit: "psi",
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
