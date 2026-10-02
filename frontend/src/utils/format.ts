/**
 * Backend Decimal fields (esp. multiplied ones like P&L) can arrive as
 * strings with many trailing-zero decimal places (e.g. "2842000.0000000000000000")
 * or in scientific notation for zero ("0E-8"). Round-tripping through
 * Number() trims both for display; these values are never fed back into
 * further math, only rendered.
 */
export function formatNum(value: string | number, maxDecimals = 8): string {
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return String(value);
  return n.toLocaleString(undefined, { maximumFractionDigits: maxDecimals });
}

/** "$1,234" -- fixed decimals so columns of dollars line up. */
export function formatUsd(value: string | number, decimals = 0): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`;
}

/** "+$1,234.50" / "-$80.00" for P&L. */
export function formatSignedUsd(value: string | number, decimals = 2): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  const sign = n > 0 ? "+" : n < 0 ? "-" : "";
  return `${sign}${formatUsd(Math.abs(n), decimals)}`;
}

export function formatPct(value: string | number, decimals = 1): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  return `${n.toFixed(decimals)}%`;
}
