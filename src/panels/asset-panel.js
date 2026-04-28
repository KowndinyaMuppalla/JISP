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
    /** @type {HTMLElement} */
    ($("#asset-risk-fill")).style.width = `${Math.round(score * 100)}%`;
    $("#asset-panel").dataset.risk = p.risk_condition_class ?? "";

    this._renderAttributes(p);

    // Reset any previous explanation
    $("#explain-body").hidden = true;
    $("#explain-text").textContent = "";
    /** @type {HTMLButtonElement} */
    ($("#explain-btn")).disabled = false;

    const panel = $("#asset-panel");
    panel.hidden = false;
    document.body.dataset.assetPanel = "open";
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
