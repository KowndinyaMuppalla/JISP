/**
 * @file Left-rail panel — region & class tree-view, overlays, collapse.
 * Owns its own state and emits change events through the supplied callback.
 */

import { $, el } from "../util/dom.js";
import { TreeView } from "./tree-view.js";

const REGIONS = [
  { code: "us",     label: "United States",  dot: "us"   },
  { code: "uk",     label: "United Kingdom", dot: "uk"   },
  { code: "anz_au", label: "Australia",      dot: "anz"  },
  { code: "anz_nz", label: "New Zealand",    dot: "anz"  },
  { code: "apac",   label: "Asia Pacific",   dot: "apac" },
];

const CLASSES = [
  { code: "water_pipe",            label: "Water pipes"      },
  { code: "water_treatment_plant", label: "Treatment plants" },
  { code: "pump_station",          label: "Pump stations"    },
  { code: "reservoir",             label: "Reservoirs"       },
  { code: "valve",                 label: "Valves"           },
  { code: "hydrant",               label: "Hydrants"         },
  { code: "sensor",                label: "Sensors"          },
  { code: "dam",                   label: "Dams"             },
  { code: "bridge",                label: "Bridges"          },
  { code: "catchment",             label: "Catchments"       },
];

export class LayerPanel {
  /**
   * @param {{
   *   onChange:      (state: { regions:string[], classes:string[],
   *                            highRiskOnly:boolean, clusters:boolean }) => void,
   *   onRegionJump?: (code: string) => void,
   *   apiClient?:    import("../api/client.js").ApiClient,
   *   useTreeView?:  boolean,
   *   onItemSelect?: (itemId: string, properties: Object, geometry: Object) => void,
   * }} opts
   */
  constructor(opts) {
    this.opts         = opts;
    this.regions      = new Set(REGIONS.map((r) => r.code));
    this.classes      = new Set(CLASSES.map((c) => c.code));
    this.clusters     = true;
    this.highRiskOnly = false;

    /** @type {TreeView|null} */
    this.treeView = opts.useTreeView
      ? new TreeView({
          onChange: (state) => {
            this.regions = new Set(state.regions);
            this.classes = new Set(state.classes);
            this._emit();
          },
          onClassSelect: (classCode, classLabel, items) => {
            this._renderClassItems(classCode, classLabel, items);
          },
          apiClient: opts.apiClient,
        })
      : null;
  }

  mount() {
    if (this.treeView) {
      this.treeView.mount();
    } else {
      this._mountRegions();
      this._mountClasses();
    }

    const closeBtn = $("#class-items-close");
    if (closeBtn) {
      closeBtn.addEventListener("click", () => {
        const sec = document.getElementById("class-items-container");
        if (sec) sec.hidden = true;
        if (this.treeView) {
          this.treeView.selectedClass = null;
          document.querySelectorAll(".tree-view__class-header").forEach((h) => {
            h.classList.remove("tree-view__class-header--selected");
          });
        }
      });
    }

    $("#overlay-clusters").addEventListener("change", (e) => {
      this.clusters = /** @type {HTMLInputElement} */ (e.target).checked;
      this._emit();
    });
    $("#overlay-highrisk").addEventListener("change", (e) => {
      this.highRiskOnly = /** @type {HTMLInputElement} */ (e.target).checked;
      this._emit();
    });

    const collapseBtn = $("#layer-collapse");
    const panel       = $("#layer-panel");
    collapseBtn.addEventListener("click", () => {
      const collapsed = panel.dataset.collapsed === "true";
      panel.dataset.collapsed = collapsed ? "false" : "true";
      document.body.dataset.layerPanel = collapsed ? "" : "collapsed";
    });
  }

  /**
   * Switch the tree-view to a new region, hiding the items panel.
   * @param {string} regionCode
   */
  async switchRegion(regionCode) {
    if (this.treeView) {
      const sec = document.getElementById("class-items-container");
      if (sec) sec.hidden = true;
      await this.treeView.loadRegion(regionCode);
      this._emit();
    }
  }

  /**
   * Render Section 2: individual assets for the selected class.
   * @param {string} classCode
   * @param {string} classLabel
   * @param {any[]} items
   */
  _renderClassItems(classCode, classLabel, items) {
    const container = document.getElementById("class-items-container");
    const list      = document.getElementById("class-items-list");
    const titleEl   = document.getElementById("class-items-title");
    if (!container || !list) return;

    if (titleEl) titleEl.textContent = classLabel;
    list.innerHTML = "";

    if (items.length === 0) {
      list.appendChild(el("li", { class: "class-item class-item--empty" }, [
        "No assets in this region.",
      ]));
    }

    for (const item of items) {
      const riskScore = item.properties && item.properties.risk_score;
      const riskCls   = riskScore >= 0.7 ? "risk--high"
                      : riskScore >= 0.5 ? "risk--medium"
                      : "risk--low";

      const li = el("li", { class: "class-item", "data-item-id": item.id }, [
        el("div", { class: "class-item__main" }, [
          el("span", { class: "class-item__code" }, [item.asset_code || item.id]),
          item.name ? el("span", { class: "class-item__name" }, [item.name]) : null,
        ]),
        riskScore != null
          ? el("span", { class: "class-item__risk " + riskCls }, [riskScore.toFixed(2)])
          : null,
      ]);

      li.addEventListener("click", () => {
        const nodes = /** @type {NodeListOf<HTMLElement>} */ (
          list.querySelectorAll(".class-item[data-item-id]")
        );
        nodes.forEach((node) => { node.dataset.selected = "false"; });
        li.dataset.selected = "true";
        if (this.opts.onItemSelect) {
          this.opts.onItemSelect(item.id, item.properties, item.geometry);
        }
      });

      list.appendChild(li);
    }

    container.hidden = false;
  }

  // Flat-toggle fallback (useTreeView = false)

  _mountRegions() {
    const ul = $("#region-toggles");
    if (!ul) return;
    ul.innerHTML = "";
    for (const r of REGIONS) {
      const li = el("li");
      const label = el("label", { class: "toggle" }, [
        el("input", { type: "checkbox", "data-region": r.code, checked: "" }),
        el("span",  { class: "toggle__track" }),
        el("span",  { class: "toggle__label" }, [
          el("span", { class: "dot dot--" + r.dot }),
          r.label,
        ]),
        el("span", { class: "toggle__count", "data-count-region": r.code }, ["0"]),
      ]);
      li.appendChild(label);
      ul.appendChild(li);
    }
    ul.addEventListener("change", (e) => {
      const t    = /** @type {HTMLInputElement} */ (e.target);
      const code = t.dataset.region;
      if (!code) return;
      if (t.checked) this.regions.add(code); else this.regions.delete(code);
      this._emit();
    });
    ul.addEventListener("dblclick", (e) => {
      const target = /** @type {HTMLElement} */ (e.target).closest("[data-region]");
      const code   = target && target.getAttribute("data-region");
      if (code && this.opts.onRegionJump) this.opts.onRegionJump(code);
    });
  }

  _mountClasses() {
    const ul = $("#class-toggles");
    if (!ul) return;
    ul.innerHTML = "";
    for (const c of CLASSES) {
      const li = el("li");
      const label = el("label", { class: "toggle" }, [
        el("input", { type: "checkbox", "data-class": c.code, checked: "" }),
        el("span",  { class: "toggle__track" }),
        el("span",  { class: "toggle__label" }, [c.label]),
        el("span",  { class: "toggle__count", "data-count-class": c.code }, ["0"]),
      ]);
      li.appendChild(label);
      ul.appendChild(li);
    }
    ul.addEventListener("change", (e) => {
      const t    = /** @type {HTMLInputElement} */ (e.target);
      const code = t.dataset.class;
      if (!code) return;
      if (t.checked) this.classes.add(code); else this.classes.delete(code);
      this._emit();
    });
  }

  /** Refresh the per-toggle count chips from the current asset collection. */
  setCounts({ regions = /** @type {Record<string,number>} */ ({}), classes = /** @type {Record<string,number>} */ ({}), clusters = 0 }) {
    for (const [code, n] of Object.entries(regions)) {
      const node = document.querySelector("[data-count-region=\"" + code + "\"]");
      if (node) node.textContent = String(n);
    }
    for (const [code, n] of Object.entries(classes)) {
      const node = document.querySelector("[data-count-class=\"" + code + "\"]");
      if (node) node.textContent = String(n);
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