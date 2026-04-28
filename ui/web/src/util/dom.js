/** Tiny DOM helpers — kept dependency-free. */

/** @param {string} sel @param {ParentNode} [root] */
export const $ = (sel, root = document) => /** @type {HTMLElement} */ (root.querySelector(sel));

/** @param {string} sel @param {ParentNode} [root] */
export const $$ = (sel, root = document) =>
  /** @type {HTMLElement[]} */ ([...root.querySelectorAll(sel)]);

/**
 * @template {keyof HTMLElementTagNameMap} K
 * @param {K} tag
 * @param {Record<string,string>|null} [attrs]
 * @param {(string|Node)[]} [children]
 * @returns {HTMLElementTagNameMap[K]}
 */
export function el(tag, attrs = null, children = []) {
  const node = document.createElement(tag);
  if (attrs) for (const [k, v] of Object.entries(attrs)) {
    if (k === "class")      node.className = v;
    else if (k === "html")  node.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function") {
      node.addEventListener(k.slice(2), /** @type any */ (v));
    }
    else node.setAttribute(k, v);
  }
  for (const c of children) {
    if (c == null) continue;
    node.append(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return node;
}

/** @param {Element} target  @param {string} html */
export function html(target, html) { target.innerHTML = html; }

/** Debounce helper. @template {(...a:any)=>any} F  @param {F} fn @param {number} ms */
export function debounce(fn, ms) {
  /** @type {ReturnType<typeof setTimeout>|null} */
  let t = null;
  return /** @type {F} */ ((...args) => {
    if (t) clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  });
}
