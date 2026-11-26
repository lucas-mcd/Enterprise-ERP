import { ErrorBoundary } from "../../../shared/components/ErrorBoundary";
import { validateCashSummary, chartCents } from "../chart-contract";
import { ChartTooltip } from "../../../shared/components/ChartTooltip";
import { useId, useMemo, useState } from "react";
import {
  Area,
  ComposedChart,
  AreaChart,
  Bar,
  Line,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Pie,
  PieChart,
  Cell,
} from "recharts";
import { safeFormatDate, money } from "../../../shared/lib/format";
const colors = [
  "#818cf8",
  "#a5b4fc",
  "#c4b5fd",
  "#64748b",
  "#94a3b8",
  "#e2e8f0",
];
export default function CashCharts(props: { summary: unknown }) {
  return (
    <ErrorBoundary resetKeys={[props.summary]}>
      <CashChartsGuard {...props} />
    </ErrorBoundary>
  );
}
/** Validate before chart arithmetic; missing/NaN amounts never become zero. */
function CashChartsGuard({ summary }: { summary: unknown }) {
  let validated: ReturnType<typeof validateCashSummary> | null = null;
  try {
    validated = validateCashSummary(summary);
  } catch {
    /* Invalid API data. */
  }
  if (!validated || !validated.points.length || !validated.total_records) {
    return (
      <section
        className="ui-card flex min-h-[260px] flex-col items-center justify-center gap-2 p-6 text-center"
        role="status"
      >
        <h2 className="card-title">Sem dados no período</h2>
        <p className="card-subtitle">
          Não há uma série financeira válida disponível. Atualize os dados ou
          ajuste os filtros.
        </p>
      </section>
    );
  }
  return <CashChartsContent summary={validated} />;
}
function CashChartsContent({ summary: input }: { summary: unknown }) {
  const summary = useMemo(() => validateCashSummary(input), [input]);
  const animate =
    typeof window !== "undefined" &&
    !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const [mode, setMode] = useState("area");
  const [visible, setVisible] = useState<Record<string, boolean>>({
    income: true,
    expense: true,
    net: true,
    forecast: false,
  });
  const id = useId().replace(/:/g, "");
  const labels: Record<string, string> = {
    income: "Receitas",
    expense: "Despesas",
    net: "Saldo Líquido",
    forecast: "Previsto",
  };
  const palette: Record<string, string> = {
    income: "#818cf8",
    expense: "#fb7185",
    net: "#34d399",
    forecast: "#fbbf24",
  };
  const points = useMemo(() => {
    const totals: Record<string, bigint> = {
      income: 0n,
      expense: 0n,
      net: 0n,
      forecast: 0n,
    };
    const cents = chartCents;
    return summary.points.map((p) => {
      const income = cents(p.income),
        expense = cents(p.expense);
      const values = {
        income,
        expense,
        net: income - expense,
        forecast:
          income - expense + cents(p.pending_income) - cents(p.pending_expense),
      };
      const row: Record<string, string | number> = { day: p.day };
      Object.entries(values).forEach(([k, v]) => {
        totals[k] = (totals[k] ?? 0n) + v;
        const plotted = mode === "cumulative" ? totals[k]! : v;
        if (
          plotted > BigInt(Number.MAX_SAFE_INTEGER) ||
          plotted < -BigInt(Number.MAX_SAFE_INTEGER)
        ) {
          throw new Error("Valor acumulado excede a precisão do gráfico.");
        }
        row[k] = Number(plotted) / 100;
      });
      return row;
    });
  }, [summary, mode]);
  const Chart = mode === "bar" || mode === "line" ? ComposedChart : AreaChart;
  const series = (
    <Chart data={points} margin={{ top: 15, right: 8, left: 0, bottom: 0 }}>
      <defs>
        {Object.keys(labels).map((k) => (
          <linearGradient key={k} id={`${id}-${k}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={palette[k]} stopOpacity={0.24} />
            <stop offset="95%" stopColor={palette[k]} stopOpacity={0.015} />
          </linearGradient>
        ))}
      </defs>
      <CartesianGrid
        stroke="var(--chart-grid)"
        vertical={false}
        strokeDasharray="3 3"
        strokeOpacity={0.45}
      />
      <XAxis
        dataKey="day"
        tickFormatter={(value: unknown) => safeFormatDate(value)}
        minTickGap={45}
        tick={{ fill: "var(--chart-text)", fontSize: 10 }}
      />
      <YAxis width={65} tick={{ fill: "var(--chart-text)", fontSize: 10 }} />
      <Tooltip
        content={(props) => (
          <ChartTooltip {...props} label={safeFormatDate(props.label)} />
        )}
        cursor={{
          stroke: "var(--chart-text)",
          strokeDasharray: "3 3",
          strokeOpacity: 0.3,
        }}
      />
      {Object.keys(labels).map((k) =>
        mode === "bar" ? (
          <Bar
            key={k}
            dataKey={k}
            name={labels[k] ?? k}
            hide={!visible[k]}
            fill={palette[k]}
            isAnimationActive={animate}
            animationDuration={250}
            radius={[3, 3, 0, 0]}
          />
        ) : mode === "area" || mode === "cumulative" ? (
          <Area
            key={k}
            type="monotone"
            dataKey={k}
            name={labels[k] ?? k}
            hide={!visible[k]}
            stroke={palette[k] ?? "#818cf8"}
            fill={`url(#${id}-${k})`}
            strokeWidth={2.5}
            activeDot={{ r: 4, strokeWidth: 3, stroke: "var(--chart-tooltip)" }}
            isAnimationActive={animate}
            animationDuration={250}
          />
        ) : (
          <Line
            key={k}
            type="monotone"
            dataKey={k}
            name={labels[k] ?? k}
            hide={!visible[k]}
            stroke={palette[k] ?? "#818cf8"}
            strokeWidth={2.5}
            dot={false}
            strokeDasharray={k === "forecast" ? "5 4" : "0"}
            isAnimationActive={animate}
            animationDuration={250}
          />
        ),
      )}
    </Chart>
  );
  const categories = summary.expense_categories.map((c) => ({
    ...c,
    value: Number(c.amount),
  }));
  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_300px]">
      <section className="ui-card min-w-0">
        <div className="flex flex-wrap justify-between gap-3 p-5">
          <div>
            <h2 className="card-title">Evolução do fluxo de caixa</h2>
            <p className="card-subtitle">
              {mode === "cumulative"
                ? "Acumulado a partir de zero no período selecionado."
                : "Movimentações diárias no período selecionado."}
            </p>
          </div>
          <select
            aria-label="Tipo de gráfico"
            className="form-input !w-36"
            value={mode}
            onChange={(e) => setMode(e.target.value)}
          >
            <option value="area">Área suave</option>
            <option value="line">Linhas</option>
            <option value="bar">Barras</option>
            <option value="cumulative">Acumulado</option>
          </select>
        </div>
        <div className="flex flex-wrap justify-between gap-3 px-5 pb-4">
          {Object.entries(labels).map(([key, label]) => (
            <label
              key={key}
              className="flex items-center gap-2 text-xs"
              style={{ color: palette[key] }}
            >
              <input
                type="checkbox"
                checked={!!visible[key]}
                onChange={() => setVisible((v) => ({ ...v, [key]: !v[key] }))}
              />
              {label}
            </label>
          ))}
          <span className="text-xs text-slate-500">
            Previsto = saldo realizado + pendências líquidas.
          </span>
        </div>
        <div className="h-[260px] min-w-0 px-4 pb-3">
          {summary.total_records ? (
            <ResponsiveContainer width="100%" height="100%" minWidth={0}>
              {series}
            </ResponsiveContainer>
          ) : (
            <div className="grid h-full place-items-center text-sm text-slate-500">
              Sem dados no período
            </div>
          )}
        </div>
        <details className="border-t border-slate-200 p-4 text-xs text-slate-500">
          <summary>Consultar dados do gráfico</summary>
          <div className="mt-3 max-h-40 overflow-auto">
            <table className="w-full text-left">
              <thead>
                <tr>
                  <th>Data</th>
                  <th>Receitas</th>
                  <th>Despesas</th>
                </tr>
              </thead>
              <tbody>
                {points.map((p, index) => (
                  <tr key={`${String(p.day)}-${index}`}>
                    <td>{p.day}</td>
                    <td>{money(Number(p.income).toFixed(2))}</td>
                    <td>{money(Number(p.expense).toFixed(2))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </section>
      <section className="ui-card p-5">
        <h2 className="card-title">Despesas por categoria</h2>
        <p className="card-subtitle">
          Previstas e realizadas, conforme filtros.
        </p>
        {categories.length ? (
          <>
            <div className="h-[190px]">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={categories}
                    dataKey="value"
                    nameKey="category"
                    innerRadius={52}
                    outerRadius={74}
                    paddingAngle={3}
                    stroke="none"
                    isAnimationActive={animate}
                    animationDuration={250}
                  >
                    {categories.map((c, i) => (
                      <Cell
                        key={`${c.category}-${i}`}
                        fill={colors[i % colors.length] ?? "#818cf8"}
                      />
                    ))}
                  </Pie>
                  <Tooltip content={(props) => <ChartTooltip {...props} />} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="space-y-3">
              {categories.map((c, i) => (
                <div className="flex gap-2 text-xs" key={`${c.category}-${i}`}>
                  <span style={{ color: colors[i % colors.length] }}>●</span>
                  <span className="text-slate-500">{c.category}</span>
                  <strong className="ml-auto">{money(c.amount)}</strong>
                </div>
              ))}
            </div>
          </>
        ) : (
          <p className="py-20 text-center text-xs text-slate-500">
            Sem despesas no período.
          </p>
        )}
      </section>
    </div>
  );
}
