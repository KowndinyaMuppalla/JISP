/**
 * @file Hierarchical tree-view component for Layer panel.
 * Section 1: Region header -> grouped asset-class rows (no inline items).
 * Clicking a class row fires onClassSelect -> populates the items panel.
 * Checking a class checkbox toggles its visibility on the map.
 */

import { el } from "../util/dom.js";

export const REGION_META = {
  us:     { label: "United States",  dot: "us"   },
  uk:     { label: "United Kingdom", dot: "uk"   },
  anz_au: { label: "Australia",      dot: "anz"  },
  anz_nz: { label: "New Zealand",    dot: "anz"  },
  apac:   { label: "Asia Pacific",   dot: "apac" },
};

export const CLASS_META = {
  water_pipe:            { label: "Water pipes",      group: "Infrastructure" },
  water_treatment_plant: { label: "Treatment plants", group: "Infrastructure" },
  pump_station:          { label: "Pump stations",    group: "Infrastructure" },
  reservoir:             { label: "Reservoirs",       group: "Water bodies"   },
  valve:                 { label: "Valves",           group: "Infrastructure" },
  hydrant:               { label: "Hydrants",         group: "Infrastructure" },
  sensor:                { label: "Sensors",          group: "Monitoring"     },
  dam:                   { label: "Dams",             group: "Water bodies"   },
  bridge:                { label: "Bridges",          group: "Infrastructure" },
  catchment:             { label: "Catchments",       group: "Water bodies"   },
};

export class TreeView {
  /**
   * @param {{
   *   onChange:       (state: { regions: string[], classes: string[] }) => void,
   *   onClassSelect?: (classCode: string, classLabel: string, items: any[]) => void,
   *   apiClient?:     import("../api/client.js").ApiClient,
   * }} opts
   */
  constructor(opts) {
    this.opts = opts;
    this.currentRegion = "us";
    /** All classes visible on the map by default. */
    this.selectedClasses = new Set(Object.keys(CLASS_META));
    /** The class whose individual items are shown in Section 2. */
    this.selectedClass = /** @type {string|null} */ (null);
    /** region -> classCode -> item[] (each item carries its geometry). */
    this.classItems = /** @type {Record<string, Record<string, any[]>>} */ ({});
  }

  /** @param {string} [containerId] */
  mount(containerId = "tree-view-container") {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.classList.add("tree-view");
    this._renderRegionTree();
  }

  /**
   * Fetch assets for a region, group by class, and rebuild the tree.
   * @param {string} regionCode
   */
  async loadRegion(regionCode) {
    const api = this.opts.apiClient;
    if (!api) return;
    this.currentRegion = regionCode;
    this.selectedClass = null;

    const assets = await api.listAssets({
      regions: /** @type {import("../api/types.js").RegionCode[]} */ ([regionCode]),
    });
    this.classItems[regionCode] = {};

    for (const f of assets.features) {
      const cc = f.properties.class_code;
      if (!cc) continue;
      if (!this.classItems[regionCode][cc]) this.classItems[regionCode][cc] = [];
      this.classItems[regionCode][cc].push({
        id:         f.properties.id,
        asset_code: f.properties.asset_code,
        name:       f.properties.name,
        class_code: cc,
        class_name: f.properties.class_name,
        properties: f.properties,
        geometry:   f.geometry,
      });
    }

    this._renderRegionTree();
  }

  _renderRegionTree() {
    const container = document.getElementById("tree-view-container");
    if (!container) return;

    const regionMeta = REGION_META[this.currentRegion];
    if (!regionMeta) return;

    container.innerHTML = "";

    container.appendChild(el("div", { class: "tree-view__header" }, [
      el("span", { class: "dot dot--" + regionMeta.dot }),
      el("h3",   { class: "tree-view__region-name" }, [regionMeta.label]),
    ]));

    const tree = el("ul", { class: "tree-view__list" });
    for (const [groupName, codes] of Object.entries(this._groupedClasses())) {
      tree.appendChild(this._renderGroup(groupName, codes));
    }
    container.appendChild(tree);
  }

  /**
   * @param {string}   groupName
   * @param {string[]} codes
   * @returns {HTMLLIElement}
   */
  _renderGroup(groupName, codes) {
    const groupLi = el("li", { class: "tree-view__group" });

    const groupHeader = el("div", { class: "tree-view__group-header" }, [
      el("span", { class: "tree-view__caret" }, ["▾"]),
      el("span", { class: "tree-view__group-name" }, [groupName]),
    ]);

    const sublist = el("ul", { class: "tree-view__sublist" });
    for (const cc of codes) {
      const meta  = CLASS_META[cc];
      const items = this.classItems[this.currentRegion]?.[cc] ?? [];
      sublist.appendChild(this._renderClassNode(cc, meta?.label ?? cc, items));
    }

    groupHeader.addEventListener("click", () => {
      const collapsed = groupHeader.classList.toggle("tree-view__group-header--collapsed");
      sublist.classList.toggle("tree-view__sublist--hidden", collapsed);
    });

    groupLi.appendChild(groupHeader);
    groupLi.appendChild(sublist);
    return groupLi;
  }

  /**
   * @param {string}   classCode
   * @param {string}   classLabel
   * @param {any[]}    items
   * @returns {HTMLLIElement}
   */
  _renderClassNode(classCode, classLabel, items) {
    const li         = el("li", { class: "tree-view__class-item" });
    const isSelected = this.selectedClass === classCode;

    const checkbox = el("input", {
      type:         "checkbox",
      class:        "tree-view__class-checkbox",
      "data-class": classCode,
    });
    checkbox.setAttribute("checked", "");

    const header = el("div", {
      class:        "tree-view__class-header" + (isSelected ? " tree-view__class-header--selected" : ""),
      "data-class": classCode,
    }, [
      checkbox,
      el("span", { class: "tree-view__class-label" }, [classLabel]),
      el("span", { class: "tree-view__count" }, [String(items.length)]),
      el("span", { class: "tree-view__class-chevron" }, ["›"]),
    ]);
    li.appendChild(header);

    checkbox.addEventListener("change", (e) => {
      e.stopPropagation();
      if (/** @type {HTMLInputElement} */ (e.target).checked) {
        this.selectedClasses.add(classCode);
      } else {
        this.selectedClasses.delete(classCode);
      }
      this._emit();
    });

    header.addEventListener("click", (e) => {
      if (e.target === checkbox) return;
      this.selectedClass = classCode;

      document.querySelectorAll(".tree-view__class-header").forEach((h) => {
        h.classList.toggle(
          "tree-view__class-header--selected",
          /** @type {HTMLElement} */ (h).dataset.class === classCode,
        );
      });

      if (this.opts.onClassSelect) {
        this.opts.onClassSelect(classCode, classLabel, items);
      }
    });

    return li;
  }

  /** @returns {Record<string, string[]>} */
  _groupedClasses() {
    /** @type {Record<string, string[]>} */
    const groups = {};
    for (const [cc, meta] of Object.entries(CLASS_META)) {
      const g = meta.group || "Other";
      if (!groups[g]) groups[g] = [];
      groups[g].push(cc);
    }
    return groups;
  }

  state() {
    return {
      regions: [this.currentRegion],
      classes: [...this.selectedClasses],
    };
  }

  _emit() {
    if (this.opts.onChange) this.opts.onChange(this.state());
  }
}