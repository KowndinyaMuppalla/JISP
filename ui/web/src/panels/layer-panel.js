/**
 * @file Left-rail panel — region & class toggles, overlays, collapse.
 * Owns its own state and emits change events through the supplied callback.
 */

import { $, el } from "../util/dom.js";

const REGIONS = [
  { code: "us",     label: "United States",  dot: "us"   },
  { code: "uk",     label: "United Kingdom", dot: "uk"   },
  { code: "anz_au", label: "Australia",      dot: "anz"  },
  { code: "anz_nz", label: "New Zealand",    dot: "anz"  },
  { code: "apac",   label: "Asia Pacific",   dot: "apac" },
];

const CLASSES = [
  { code: "water_pipe",            label: "Water pipes" },
  { code: "water_treatment_plant", label: "Treatment plants" },
  { code: "pump_station",          label: "Pump stations" },
  { code: "reservoir",             label: "Reservoirs" },
  { code: "valve",                 label: "Valves" },
  { code: "hydrant",               label: "Hydrants" },
  { code: "sensor",                label: "Sensors" },
  { code: "dam",                   label: "Dams" },
  { code: "bridge",                label: "Bridges" },
  { code: "catchment",             label: "Catchments" },
];

export class LayerPanel {
  /**
   * @param {{
   *   onChange: (state: { regions:string[], classes:string[],
   *                       highRiskOnly:boolean, clusters:boolean }) => void,
   *   onRegionJump?: (code: string) => void,
   * }} opts
   */
  constructor(opts) {
    this.opts = opts;
    /** @type {Set<string>} */ this.regions  = new Set(REGIONS.map((r) => r.code));
    /** @type {Set<string>} */ this.classes  = new Set(CLASSES.map((c) => c.code));
    this.clusters     = true;
    this.highRiskOnly = false;
    this._counts = /** @type {Record<string, number>} */ ({});
  }

  /** Mount on the existing #region-toggles + #class-toggles UL elements. */
  mount() {
    this._mountRegions();
    this._mountClasses();

    $("#overlay-clusters").addEventListener("change", (e) => {
      this.clusters = /** @type {HTMLInputElement} */(e.target).checked;
      this._emit();
    });
    $("#overlay-highrisk").addEventListener("change", (e) => {
      this.highRiskOnly = /** @type {HTMLInputElement} */(e.target).checked;
      this._emit();
    });

    const collapseBtn = $("#layer-collapse");
    const panel = $("#layer-panel");
    collapseBtn.addEventListener("click", () => {
      const collapsed = panel.dataset.collapsed === "true";
      panel.dataset.collapsed = collapsed ? "false" : "true";
      document.body.dataset.layerPanel = collapsed ? "" : "collapsed";
    });
  }

  _mountRegions() {
    const ul = $("#region-toggles");
    ul.innerHTML = "";
    for (const r of REGIONS) {
      const li = el("li");
      const label = el("label", { class: "toggle" }, [
        el("input", { type: "checkbox", "data-region": r.code, checked: "" }),
        el("span", { class: "toggle__track" }),
        el("span", { class: "toggle__label" }, [
          el("span", { class: `dot dot--${r.dot}` }),
          r.label,
        ]),
        el("span", { class: "toggle__count", "data-count-region": r.code }, ["0"]),
      ]);
      li.appendChild(label);
      ul.appendChild(li);
    }
    ul.addEventListener("change", (e) => {
      const t = /** @type {HTMLInputElement} */ (e.target);
      const code = t.dataset.region;
      if (!code) return;
      if (t.checked) this.regions.add(code); else this.regions.delete(code);
      this._emit();
    });

    // Region jump: clicking the row label flies to that region.
    ul.addEventListener("dblclick", (e) => {
      const target = /** @type {HTMLElement} */ (e.target).closest("[data-region]");
      const code = target?.getAttribute("data-region");
      if (code && this.opts.onRegionJump) this.opts.onRegionJump(code);
    });
  }

  _mountClasses() {
    const ul = $("#class-toggles");
    ul.innerHTML = "";
    for (const c of CLASSES) {
      const li = el("li");
      const label = el("label", { class: "toggle" }, [
        el("input", { type: "checkbox", "data-class": c.code, checked: "" }),
        el("span", { class: "toggle__track" }),
        el("span", { class: "toggle__label" }, [c.label]),
        el("span", { class: "toggle__count", "data-count-class": c.code }, ["0"]),
      ]);
      li.appendChild(label);
      ul.appendChild(li);
    }
    ul.addEventListener("change", (e) => {
      const t = /** @type {HTMLInputElement} */ (e.target);
      const code = t.dataset.class;
      if (!code) return;
      if (t.checked) this.classes.add(code); else this.classes.delete(code);
      this._emit();
    });
  }

  /** Refresh the per-toggle count chips from the current asset collection. */
  setCounts({ regions = {}, classes = {}, clusters = 0 }) {
    for (const [code, n] of Object.entries(regions)) {
      const el = document.querySelector(`[data-count-region="${code}"]`);
      if (el) el.textContent = String(n);
    }
    for (const [code, n] of Object.entries(classes)) {
      const el = document.querySelector(`[data-count-class="${code}"]`);
      if (el) el.textContent = String(n);
    }
    const cc = $("#overlay-clusters-count");
    if (cc) cc.textContent = String(clusters);
  }

  state() {
    return {
      regions:      [...this.regions],
      classes:      [...this.classes],
      clusters:     this.clusters,
      highRiskOnly: this.highRiskOnly,
    };
  }

  _emit() { this.opts.onChange(this.state()); }
}
