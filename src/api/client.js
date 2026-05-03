/**
 * @file API Client - Connects to live backend at http://localhost:8000
 * Supports both live API and fallback to mocks
 */

import "./types.js";
import * as mocks from "./mocks.js";

const DEFAULT_TIMEOUT_MS = 15000;

export class ApiClient {
  /**
   * @param {{ baseUrl?: string, mode?: "mock"|"live"|"auto" }} [opts]
   */
  constructor(opts = {}) {
    this.baseUrl = (opts.baseUrl ?? "http://localhost:8000").replace(/\/$/, "");
    this.mode    = opts.mode ?? "live";
    this._live   = false;
    this._probe  = null;
  }

  get isLive() { return this._live; }

  async probe() {
    if (this.mode === "mock") { this._live = false; return; }
    if (this.mode === "live") {
      this._live = true;
      return;
    }
    if (this._probe) return this._probe;
    this._probe = (async () => {
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

  async _fetch(path, init = {}) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), DEFAULT_TIMEOUT_MS);
    try {
      const res = await fetch(`${this.baseUrl}${path}`, { ...init, signal: ctrl.signal });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } finally {
      clearTimeout(timer);
    }
  }

  async listAssets(filters = {}) {
    if (!this._live) return mocks.mockListAssets(filters);
    
    const qs = new URLSearchParams();
    if (filters.regions?.length) qs.set("regions", filters.regions.join(","));
    if (filters.classes?.length) qs.set("classes", filters.classes.join(","));
    if (filters.highRiskOnly) qs.set("high_risk_only", "true");
    
    try {
      const data = await this._fetch(`/api/v1/assets?${qs.toString()}`);
      
      // Convert backend format to GeoJSON
      if (data.assets && Array.isArray(data.assets)) {
        return {
          type: "FeatureCollection",
          features: data.assets.map(asset => ({
            type: "Feature",
            geometry: {
              type: "Point",
              coordinates: [parseFloat(asset.lon), parseFloat(asset.lat)]
            },
            properties: {
              id: asset.asset_id,
              asset_code: asset.name,
              name: asset.name,
              class_code: this._mapClassCode(asset.asset_class),
              class_name: asset.asset_class,
              region_code: asset.region_code,
              region_name: asset.region_code,
              risk_score: asset.risk_score > 1 ? asset.risk_score / 100 : asset.risk_score,
              material_name: asset.material,
              install_year: asset.install_year
            }
          }))
        };
      }
      return data;
    } catch (err) {
      console.warn("Live API failed, falling back to mocks:", err);
      this._live = false;
      return mocks.mockListAssets(filters);
    }
  }

  async getAsset(id) {
    if (!this._live) return mocks.mockGetAsset(id);
    
    try {
      const asset = await this._fetch(`/api/v1/assets/${encodeURIComponent(id)}`);
      if (!asset) return null;
      
      return {
        type: "Feature",
        geometry: {
          type: "Point",
          coordinates: [parseFloat(asset.lon), parseFloat(asset.lat)]
        },
        properties: {
          id: asset.asset_id,
          asset_code: asset.name,
          name: asset.name,
          class_code: this._mapClassCode(asset.asset_class),
          class_name: asset.asset_class,
          region_code: asset.region_code,
          region_name: asset.region_code,
          risk_score: asset.risk_score > 1 ? asset.risk_score / 100 : asset.risk_score,
          material_name: asset.material,
          install_year: asset.install_year
        }
      };
    } catch (err) {
      console.warn("Live API failed, falling back to mocks:", err);
      this._live = false;
      return mocks.mockGetAsset(id);
    }
  }

  async listClusterZones() {
    if (!this._live) return mocks.mockListClusterZones();
    try {
      return await this._fetch(`/api/v1/cluster-zones?active=true`);
    } catch {
      return mocks.mockListClusterZones();
    }
  }

  async searchAssets(q) {
    if (!this._live) return mocks.mockSearchAssets(q);
    if (!q || q.length < 2) return [];
    
    try {
      const data = await this._fetch(`/api/v1/assets/search?q=${encodeURIComponent(q)}`);
      
      if (data.assets && Array.isArray(data.assets)) {
        return data.assets.map(asset => ({
          type: "Feature",
          geometry: {
            type: "Point",
            coordinates: [parseFloat(asset.lon), parseFloat(asset.lat)]
          },
          properties: {
            id: asset.asset_id,
            asset_code: asset.name,
            name: asset.name,
            class_code: this._mapClassCode(asset.asset_class),
            class_name: asset.asset_class,
            region_code: asset.region_code,
            risk_score: asset.risk_score > 1 ? asset.risk_score / 100 : asset.risk_score
          }
        }));
      }
      return data;
    } catch {
      return mocks.mockSearchAssets(q);
    }
  }

  async explain(req) {
    if (!this._live) return mocks.mockExplain(req);
    try {
      return await this._fetch(`/explain`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(req)
      });
    } catch {
      return mocks.mockExplain(req);
    }
  }

  async upload(file) {
    if (!this._live) return mocks.mockUpload(file);
    try {
      const fd = new FormData();
      fd.append("file", file);
      return await this._fetch(`/api/v1/import/upload`, { method: "POST", body: fd });
    } catch {
      return mocks.mockUpload(file);
    }
  }

  async observations(id, opts = {}) {
    if (!this._live) return mocks.mockObservations(id, opts);
    try {
      const qs = new URLSearchParams();
      if (opts.metric) qs.set("metric", opts.metric);
      if (opts.from)   qs.set("from", opts.from);
      if (opts.to)     qs.set("to", opts.to);
      return await this._fetch(`/api/v1/assets/${encodeURIComponent(id)}/observations?${qs.toString()}`);
    } catch {
      return mocks.mockObservations(id, opts);
    }
  }

  subscribeStream(id, onPoint) {
    if (!this._live) {
      const t = setInterval(() => {
        onPoint({
          time: new Date().toISOString(),
          value: +(60 + Math.random() * 12).toFixed(2),
          unit: "psi"
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

  _mapClassCode(className) {
    const map = {
      "PIPE_W": "water_pipe",
      "SENSOR": "sensor",
      "WTP": "water_treatment_plant",
      "PUMP": "pump_station",
      "VALVE": "valve",
      "HYDRANT": "hydrant",
      "DAM": "dam",
      "RESERVOIR": "reservoir"
    };
    return map[className] || className;
  }
}
