/**
 * @file Top-bar asset search. Debounced query → ApiClient.searchAssets().
 * Keyboard nav (↑ ↓ Enter Esc), `/` shortcut to focus.
 */

import { $, el, debounce } from "../util/dom.js";
import { fmtScore } from "../util/format.js";

export class SearchBox {
  /**
   * @param {{
   *   apiClient: import("../api/client.js").ApiClient,
   *   onPick: (feature: import("../api/types.js").AssetFeature) => void,
   * }} opts
   */
  constructor(opts) {
    this.api = opts.apiClient;
    this.onPick = opts.onPick;
    /** @type {import("../api/types.js").AssetFeature[]} */ this._results = [];
    this._activeIdx = -1;
  }

  mount() {
    const input = /** @type {HTMLInputElement} */ ($("#search-input"));
    const list  = /** @type {HTMLElement} */ ($("#search-results"));

    const search = debounce(async (q) => {
      if (!q || q.length < 2) {
        this._results = []; list.hidden = true; return;
      }
      const features = await this.api.searchAssets(q);
      this._results = features;
      this._activeIdx = features.length ? 0 : -1;
      this._render();
    }, 180);

    input.addEventListener("input", () => search(input.value.trim()));
    input.addEventListener("focus", () => { if (this._results.length) list.hidden = false; });
    input.addEventListener("blur",  () => setTimeout(() => (list.hidden = true), 150));

    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); this._move(+1); }
      if (e.key === "ArrowUp")   { e.preventDefault(); this._move(-1); }
      if (e.key === "Enter" && this._activeIdx >= 0) {
        e.preventDefault();
        this._pick(this._results[this._activeIdx]);
      }
      if (e.key === "Escape") { input.blur(); list.hidden = true; }
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "/" && document.activeElement?.tagName !== "INPUT") {
        e.preventDefault();
        input.focus();
        input.select();
      }
    });
  }

  _move(delta) {
    if (!this._results.length) return;
    this._activeIdx = (this._activeIdx + delta + this._results.length) % this._results.length;
    this._render();
  }

  _render() {
    const list = $("#search-results");
    list.innerHTML = "";
    if (!this._results.length) { list.hidden = true; return; }
    list.hidden = false;
    this._results.forEach((f, i) => {
      const p = f.properties;
      const row = el("div", {
        class: "search-result",
        "aria-selected": i === this._activeIdx ? "true" : "false",
      }, [
        el("span", { class: "search-result__name" }, [p.name ?? p.asset_code ?? p.id]),
        el("span", { class: "search-result__meta" },
          [`${p.class_name ?? p.class_code} · ${p.region_code} · risk ${fmtScore(p.risk_score ?? 0)}`]),
      ]);
      row.addEventListener("mousedown", (e) => { e.preventDefault(); this._pick(f); });
      list.append(row);
    });
  }

  _pick(feature) {
    if (!feature) return;
    /** @type {HTMLInputElement} */ ($("#search-input")).value = feature.properties.name ?? "";
    $("#search-results").hidden = true;
    this.onPick(feature);
  }
}
