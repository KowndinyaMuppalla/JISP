/**
 * @file Import dropzone modal — UI only, calls ApiClient.upload() (mocked).
 * Real ingestion lives behind STEP 6 in the backend roadmap.
 */

import { $, el } from "../util/dom.js";
import { fmtBytes } from "../util/format.js";

const ACCEPTED_EXT = /\.(gpkg|zip|shp|geojson|json)$/i;

export class ImportPanel {
  /** @param {{ apiClient: import("../api/client.js").ApiClient }} opts */
  constructor(opts) { this.api = opts.apiClient; }

  mount() {
    $("#import-btn").addEventListener("click", () => this.open());
    const modal = $("#import-modal");
    modal.querySelectorAll("[data-close]").forEach((b) =>
      b.addEventListener("click", () => this.close())
    );
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !modal.hasAttribute("hidden")) this.close();
    });

    const dz = /** @type {HTMLElement} */ ($("#dropzone"));
    const input = /** @type {HTMLInputElement} */ ($("#dropzone-input"));

    $("#dropzone-browse").addEventListener("click", () => input.click());
    dz.addEventListener("click", (e) => {
      if (/** @type {HTMLElement} */ (e.target).id !== "dropzone-browse") input.click();
    });
    dz.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); }
    });
    input.addEventListener("change", () => {
      if (input.files) this._handleFiles([...input.files]);
      input.value = "";
    });

    ["dragenter", "dragover"].forEach((evt) =>
      dz.addEventListener(evt, (e) => {
        e.preventDefault();
        dz.dataset.active = "true";
      })
    );
    ["dragleave", "drop"].forEach((evt) =>
      dz.addEventListener(evt, (e) => {
        e.preventDefault();
        dz.dataset.active = "false";
      })
    );
    dz.addEventListener("drop", (e) => {
      const files = [...(e.dataTransfer?.files ?? [])];
      if (files.length) this._handleFiles(files);
    });
  }

  open()  { $("#import-modal").hidden = false; }
  close() { $("#import-modal").hidden = true;  }

  /** @param {File[]} files */
  async _handleFiles(files) {
    const list = $("#upload-list");
    for (const f of files) {
      const item = el("li", null, [
        el("span", { class: "upload-list__name" }, [f.name]),
        el("span", { class: "upload-list__size" }, [fmtBytes(f.size)]),
        el("span", { class: "upload-list__status" }, ["uploading…"]),
      ]);
      list.prepend(item);

      if (!ACCEPTED_EXT.test(f.name)) {
        const status = item.querySelector(".upload-list__status");
        if (status) {
          status.textContent = "rejected: unsupported format";
          status.classList.add("upload-list__status--err");
        }
        continue;
      }

      try {
        const resp = await this.api.upload(f);
        const status = item.querySelector(".upload-list__status");
        if (status) {
          status.textContent = `${resp.feature_count ?? "?"} features ${resp.status}`;
        }
      } catch (err) {
        const status = item.querySelector(".upload-list__status");
        if (status) {
          status.textContent = `error: ${err}`;
          status.classList.add("upload-list__status--err");
        }
      }
    }
  }
}
