/** Display-only date handling. Never use these fallbacks to submit business dates. */
export function safeText(value: unknown, fallback = "--"): string {
  if (typeof value !== "string") return fallback;
  // React renders this as text (never HTML). Bound size and strip control/bidi chars.
  const text = value
    .replace(/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/g, "")
    .trim()
    .slice(0, 120);
  return text || fallback;
}

function calendarDate(value: string): Date | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const date = new Date(`${value}T00:00:00.000Z`);
  if (Number.isNaN(date.getTime())) return null;
  // JS normalizes 2026-02-30 to March: reject, rather than display another day.
  return date.toISOString().slice(0, 10) === value ? date : null;
}

/** Only ISO calendar dates and timestamps with an explicit offset are formatted.
 * Other values remain text. This helper is for display, never business validation.
 */
export function safeFormatDate(
  value: unknown,
  options: Intl.DateTimeFormatOptions = { day: "2-digit", month: "short" },
): string {
  if (value === null || value === undefined) return "--";
  let text: string;
  try {
    text = String(value);
  } catch {
    return "--";
  }
  if (!text.trim()) return "--";
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(text);
  const timestamp =
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$/.test(
      text,
    );
  // Do not ask Date to interpret grouping keys or free-form labels.
  if (!dateOnly && !timestamp) return text;
  try {
    if (!calendarDate(text.slice(0, 10))) return text;
    if (
      timestamp &&
      (Number(text.slice(11, 13)) > 23 ||
        Number(text.slice(14, 16)) > 59 ||
        Number(text.slice(17, 19)) > 59)
    )
      return text;
    const date = new Date(text);
    if (Number.isNaN(date.getTime())) return text;
    return new Intl.DateTimeFormat("pt-BR", {
      timeZone: "America/Sao_Paulo",
      ...options,
      ...(dateOnly ? { timeZone: "UTC" } : {}),
    }).format(date);
  } catch {
    return text;
  }
}

export const safeDateTime = (value: unknown): string =>
  safeFormatDate(value, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

/** TanStack Query supplies dataUpdatedAt as epoch milliseconds, not an API date. */
export function safeTime(value: unknown): string {
  let input = value;
  if (typeof value === "number" && Number.isFinite(value)) {
    const date = new Date(value);
    if (!Number.isNaN(date.getTime())) input = date.toISOString();
  }
  return safeFormatDate(input, { hour: "2-digit", minute: "2-digit" });
}
export const formatDate = (value: unknown): string => safeFormatDate(value);
export const formatDateTime = (value: unknown): string => safeDateTime(value);

// Money is never calculated with Number in the browser. Decimal arithmetic lives in Python.
export function money(value: unknown): string {
  if (
    typeof value !== "string" ||
    !/^-?\d+(?:\.\d{1,4})?$/.test(value) ||
    value.length > 40
  )
    return "--";
  const negative = value.startsWith("-");
  const [whole = "0", cents = "00"] = value.replace(/^-/, "").split(".");
  return `${negative ? "− " : ""}R$ ${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ".")},${cents.padEnd(2, "0").slice(0, 2)}`;
}
/** Compatibility alias: all legacy date labels now use the same guarded parser. */
export function dateLabel(value: unknown): string {
  return safeFormatDate(value);
}
export function isoToday(): string {
  const now = new Date();
  if (Number.isNaN(now.getTime())) return "--";
  const iso = now.toISOString();
  const label = safeFormatDate(iso, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  const parts = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(label);
  return parts ? `${parts[3]}-${parts[2]}-${parts[1]}` : iso.slice(0, 10);
}
export function rangeDays(days: number) {
  const end = isoToday();
  const start = new Date(`${end}T12:00:00`);
  start.setDate(start.getDate() - days + 1);
  return {
    start_date: `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, "0")}-${String(start.getDate()).padStart(2, "0")}`,
    end_date: end,
  };
}
export function parseMoney(value: string): string | null {
  const normalized = value.trim().replace(/\s/g, "");
  // Brazilian notation: comma for decimals, optional dot thousands separators.
  if (!/^(?:\d{1,9}|\d{1,3}(?:\.\d{3}){1,2})(?:,\d{1,2})?$/.test(normalized))
    return null;
  const [whole = "0", cents = "00"] = normalized.replace(/\./g, "").split(",");
  if (whole.length > 9) return null;
  const result = `${whole.replace(/^0+(?=\d)/, "")}.${cents.padEnd(2, "0")}`;
  return result === "0.00" ? null : result;
}
