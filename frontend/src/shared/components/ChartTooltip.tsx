import { safeText } from "../lib/dates";
import { money } from "../lib/format";
export function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean | undefined;
  payload?:
    | ReadonlyArray<{
        name?: string | number | undefined;
        value?: unknown;
        color?: string | undefined;
      }>
    | undefined;
  label?: unknown;
}) {
  if (!active || !Array.isArray(payload) || !payload.length) return null;
  return (
    <div className="chart-glass">
      <p className="mb-3 text-[10px] font-semibold uppercase tracking-widest text-slate-400">
        {safeText(label, "Detalhamento")}
      </p>
      <div className="space-y-2.5">
        {payload
          .filter((p) => p && typeof p === "object")
          .map((p, i) => (
            <div key={i} className="flex min-w-44 items-center gap-3 text-xs">
              <span
                className="h-2 w-2 rounded-full"
                style={{ background: p.color ?? "#818cf8" }}
              />
              <span className="text-slate-500">{safeText(p.name)}</span>
              <strong className="ml-auto tabular-nums">
                {typeof p.value === "number" && Number.isFinite(p.value)
                  ? money(p.value.toFixed(2))
                  : money(p.value)}
              </strong>
            </div>
          ))}
      </div>
    </div>
  );
}
