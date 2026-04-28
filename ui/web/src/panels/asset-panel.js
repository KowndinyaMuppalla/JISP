/**
 * @file Right-rail panel — asset detail + /explain integration.
 * Renders pure DOM updates from a feature; calls ApiClient.explain() on demand.
 */

import "../api/types.js";
import { $, el } from "../util/dom.js";
import { fmtBytes, fmtDate, fmtMetres, fmtMillimetres, fmtScore, titleCase } from "../util/format.js";

export class AssetPanel {
  /**
   * @param {{ apiClient: import("../api/client.js").ApiClient }} opts
   */
  constructor(opts) {
    this.api = opts.apiClient;
    /** @type {import("../api/types.js").AssetFeature|null} */ this.current = null;
  }

  mount() {
    $("#asset-close").addEventListener("click", () => this.close());
    $("#explain-btn").addEventListener("click", () => this._runExplain());
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && this._isOpen()) this.close();
    });
  }

  /** @param {import("../api/types.js").AssetFeature} feature */
  show(feature) {
    this.current = feature;
    const p = feature.properties;

    $("#asset-class").textContent = p.class_name ?? p.class_code ?? "—";
    $("#asset-name").textContent  = p.name ?? p.asset_code ?? "—";
    $("#asset-code").textContent  = p.asset_code ?? "—";

    const score = p.risk_score ?? 0;
    $("#asset-risk-score").textContent = fmtScore(score);
    $("#asset-risk-class").textContent = (p.risk_condition_class ?? "—").toUpperCase();

    // Risk ring: animate stroke-dashoffset from full circumference to
    // (1 - score) * circumference. Circumference = 2 * π * r where r=42.
    const ring = /** @type {SVGCircleElement|null} */ (
      document.getElementById("asset-risk-ring")
    );
    if (ring) {
      const C = 2 * Math.PI * 42;
      ring.style.strokeDasharray  = String(C);
      ring.style.strokeDashoffset = String(C * (1 - score));
    }

    $("#asset-panel").dataset.risk = p.risk_condition_class ?? "";

    this._renderAttributes(p);
    this._renderSparkline(p.id).catch((err) => console.warn("[sparkline]", err));

    // Reset any previous explanation
    $("#explain-body").hidden = true;
    $("#explain-text").textContent = "";
    /** @type {HTMLButtonElement} */
    ($("#explain-btn")).disabled = false;

    const panel = $("#asset-panel");
    panel.hidden = false;
    panel.setAttribute("data-state", "open");
    // Re-trigger the entry animation by toggling the attribute.
    void panel.offsetWidth;
    document.body.dataset.assetPanel = "open";
  }

  /**
   * Pulls 30 days of pressure observations and renders an inline SVG
   * sparkline. The sparkline auto-rescales to fit the SVG viewBox.
   * @param {string} assetId
   */
  async _renderSparkline(assetId) {
    const obs = await this.api.observations(assetId, { metric: "pressure_psi" });
    const points = obs.points;
    if (!points.length) return;

    const W = 320, H = 60, PAD = 4;
    const values = points.map((p) => p.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = (max - min) || 1;

    const xs = points.map((_, i) => PAD + (i / (points.length - 1)) * (W - PAD * 2));
    const ys = values.map((v) => H - PAD - ((v - min) / range) * (H - PAD * 2));

    const linePath = xs.map((x, i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${ys[i].toFixed(1)}`).join(" ");
    const areaPath = `${linePath} L${xs[xs.length - 1].toFixed(1)},${H} L${xs[0].toFixed(1)},${H} Z`;

    const lineEl = /** @type {SVGPathElement} */ (document.getElementById("sparkline-line"));
    const areaEl = /** @type {SVGPathElement} */ (document.getElementById("sparkline-area"));
    const dotEl  = /** @type {SVGCircleElement} */ (document.getElementById("sparkline-dot"));
    if (lineEl) {
      lineEl.setAttribute("d", linePath);
      // Reset draw-on animation so it re-plays on every asset selection.
      const total = lineEl.getTotalLength?.() ?? 1000;
      lineEl.style.strokeDasharray  = String(total);
      lineEl.style.strokeDashoffset = String(total);
      requestAnimationFrame(() => {
        lineEl.style.transition = "stroke-dashoffset 700ms cubic-bezier(.2,.8,.2,1)";
        lineEl.style.strokeDashoffset = "0";
      });
    }
    if (areaEl) areaEl.setAttribute("d", areaPath);
    if (dotEl) {
      dotEl.setAttribute("cx", xs[xs.length - 1].toFixed(1));
      dotEl.setAttribute("cy", ys[ys.length - 1].toFixed(1));
    }

    // Stat strip: latest reading + delta vs. first observation.
    const last = values[values.length - 1];
    const first = values[0];
    const delta = last - first;
    const deltaPct = (delta / first) * 100;
    const cur = document.getElementById("obs-current");
    const del = document.getElementById("obs-delta");
    if (cur) cur.textContent = last.toFixed(1);
    if (del) {
      del.textContent = `${delta >= 0 ? "+" : ""}${deltaPct.toFixed(1)}%`;
      del.dataset.trend = delta >= 0 ? "up" : "down";
    }
  }

  close() {
    this.current = null;
    const panel = $("#asset-panel");
    panel.hidden = true;
    document.body.dataset.assetPanel = "hidden";
  }

  _isOpen() { return !$("#asset-panel").hidden; }

  /** @param {import("../api/types.js").AssetProperties} p */
  _renderAttributes(p) {
    const dl = $("#asset-attributes");
    dl.innerHTML = "";

    /** @param {string} k @param {string} v */
    const row = (k, v) => {
      dl.append(el("dt", null, [k]));
      dl.append(el("dd", null, [v]));
    };

    row("Region", p.region_name ?? p.region_code ?? "—");
    row("Class",  p.class_name  ?? p.class_code  ?? "—");
    if (p.material_name) row("Material", p.material_name);
    if (p.install_year)  row("Installed", String(p.install_year));
    if (p.diameter_mm)   row("Diameter", fmtMillimetres(p.diameter_mm));
    if (p.length_m)      row("Length",   fmtMetres(p.length_m));
    if (p.risk_computed_at) row("Risk last computed", fmtDate(p.risk_computed_at));
    if (p.attributes) {
      for (const [k, v] of Object.entries(p.attributes)) {
        if (v == null || typeof v === "object") continue;
        row(titleCase(k), String(v));
      }
    }
  }

  async _runExplain() {
    if (!this.current) return;
    const btn = /** @type {HTMLButtonElement} */ ($("#explain-btn"));
    btn.disabled = true;
    btn.textContent = "Generating…";

    try {
      const resp = await this.api.explain({
        subject: this.current.properties.id,
        template: "asset_condition",
      });

      $("#explain-text").textContent = resp.explanation;
      $("#explain-model").textContent = resp.meta.model;

      const ul = $("#explain-shap");
      ul.innerHTML = "";
      for (const d of resp.drivers) {
        const negative = d.value < 0;
        ul.append(
          el("li", null, [
            el("span", { class: "shap-bars__label" }, [titleCase(d.feature)]),
            el("span", { class: "shap-bars__track" }, [
              el("span", {
                class: `shap-bars__fill ${negative ? "shap-bars__fill--neg" : ""}`,
                style: `width:${Math.round((d.normalized ?? 0) * 100)}%`,
              }),
            ]),
            el("span", { class: "shap-bars__value" }, [
              `${d.value > 0 ? "+" : ""}${d.value.toFixed(2)}`,
            ]),
          ]),
        );
      }

      const meta = $("#explain-meta");
      meta.innerHTML = "";
      meta.append(el("span", null, [`latency ${resp.meta.latency_ms} ms`]));
      if (resp.meta.tokens_in)  meta.append(el("span", null, [`in ${resp.meta.tokens_in}t`]));
      if (resp.meta.tokens_out) meta.append(el("span", null, [`out ${resp.meta.tokens_out}t`]));
      meta.append(el("span", null, [fmtDate(resp.meta.created_at)]));

      $("#explain-body").hidden = false;
    } catch (err) {
      $("#explain-text").textContent = `Error generating explanation: ${err}`;
      $("#explain-body").hidden = false;
    } finally {
      btn.disabled = false;
      btn.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
        <path d="M12 2 14.39 8.26 21 9l-5 4.74L17.18 21 12 17.27 6.82 21 8 13.74 3 9l6.61-.74L12 2Z"
              fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" />
        </svg> Generate explanation`;
    }
  }
}

// Touch unused fmtBytes import for tree-shake-friendliness. (No-op runtime cost.)
void fmtBytes;
