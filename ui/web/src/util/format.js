/** Number / date / coord formatters. */

/** @param {number} n  @param {number} [d=2] */
export const fmtNum = (n, d = 2) => (n == null ? "—" : n.toFixed(d));

/** @param {number} m */
export function fmtMetres(m) {
  if (m == null) return "—";
  if (m < 1000) return `${m.toFixed(0)} m`;
  return `${(m / 1000).toFixed(2)} km`;
}

/** @param {number} mm */
export function fmtMillimetres(mm) {
  if (mm == null) return "—";
  return `${mm.toFixed(0)} mm`;
}

/** @param {number} score */
export function fmtScore(score) {
  if (score == null || Number.isNaN(score)) return "—";
  return score.toFixed(2);
}

/** @param {number} lon @param {number} lat */
export function fmtLonLat(lon, lat) {
  return `${lat.toFixed(4)}, ${lon.toFixed(4)}`;
}

/** @param {string} iso */
export function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

/** @param {number} bytes */
export function fmtBytes(bytes) {
  if (bytes == null) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  while (bytes >= 1024 && i < units.length - 1) { bytes /= 1024; i++; }
  return `${bytes.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

/** @param {string} s */
export function titleCase(s) {
  if (!s) return s;
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
