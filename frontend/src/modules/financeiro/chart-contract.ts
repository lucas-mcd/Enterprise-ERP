import type { Summary } from "./types";
import { safeText } from "../../shared/lib/dates";
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("Invalid chart object");
  return value as Record<string, unknown>;
}
function array(value: unknown): unknown[] {
  if (!Array.isArray(value) || value.length > 10000)
    throw new Error("Invalid chart collection");
  return value;
}
export function chartCents(value: unknown): bigint {
  if (typeof value !== "string" || !/^-?\d{1,16}(?:\.\d{1,2})?$/.test(value))
    throw new Error("Invalid chart decimal");
  const negative = value.startsWith("-"),
    [whole = "0", fraction = "00"] = value.replace(/^-/, "").split(".");
  const cents = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0"));
  if (cents > BigInt(Number.MAX_SAFE_INTEGER))
    throw new Error("Chart decimal out of range");
  return negative ? -cents : cents;
}
function decimal(value: unknown): string {
  chartCents(value);
  return value as string;
}
export function validateCashSummary(input: unknown): Summary {
  const row = object(input);
  if (row.source !== "demo" && row.source !== "real")
    throw new Error("Invalid chart source");
  if (
    typeof row.total_records !== "number" ||
    !Number.isSafeInteger(row.total_records) ||
    row.total_records < 0
  )
    throw new Error("Invalid chart count");
  return {
    source: row.source,
    total_records: row.total_records,
    income: decimal(row.income),
    expense: decimal(row.expense),
    net: decimal(row.net),
    pending_income: decimal(row.pending_income),
    pending_expense: decimal(row.pending_expense),
    points: array(row.points).map((value) => {
      const p = object(value);
      return {
        day: safeText(p.day),
        income: decimal(p.income),
        expense: decimal(p.expense),
        pending_income: decimal(p.pending_income),
        pending_expense: decimal(p.pending_expense),
      };
    }),
    expense_categories: array(row.expense_categories).map((value) => {
      const p = object(value);
      return { category: safeText(p.category), amount: decimal(p.amount) };
    }),
  };
}
