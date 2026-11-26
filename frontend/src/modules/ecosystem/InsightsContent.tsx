import { ChartTooltip } from "../../shared/components/ChartTooltip";
import { useState, useId } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  BarChart,
  AreaChart,
  Area,
  Bar,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { request, errorMessage } from "../../shared/api/client";
import { useAuth } from "../identity/hooks/auth-store";
import { money, parseMoney } from "../../shared/lib/format";
import { categories } from "../financeiro/types";
type Sales = {
  ticket: string;
  margin: string | null;
  cost_coverage: string;
  categories: { name: string; amount: string }[];
  sellers: { name: string; amount: string }[];
};
type Overview = {
  sales: Sales | null;
  turnover: string | null;
  delinquency: string;
  budgets: Record<string, string>[];
};
export default function Insights({
  source,
  start,
  end,
  salesOnly = false,
}: {
  source: string;
  start: string;
  end: string;
  salesOnly?: boolean;
}) {
  const gradientId = useId().replace(/:/g, "");
  const user = useAuth((s) => s.session!.user),
    client = useQueryClient();
  const [group, setGroup] = useState("categories"),
    [visible, setVisible] = useState<Record<string, boolean>>({
      budget_income: true,
      actual_income: true,
      budget_expense: true,
      actual_expense: true,
    });
  const [editing, setEditing] = useState(false);
  const data = useQuery({
    queryKey: [
      "bi",
      user.tenant_id,
      user.user_id,
      source,
      start,
      end,
      salesOnly,
    ],
    queryFn: () =>
      request<Overview | Sales>(
        `/bi/${salesOnly ? "vendas" : "overview"}?${new URLSearchParams({ source, start_date: start, end_date: end })}`,
      ),
    retry: false,
  });
  const save = useMutation({
    mutationFn: (body: Record<string, string>) =>
      request("/bi/orcamento", { method: "PUT", body: JSON.stringify(body) }),
    onSuccess: () => {
      setEditing(false);
      void client.invalidateQueries({ queryKey: ["bi"] });
    },
  });
  const overview = data.data && "budgets" in data.data ? data.data : null;
  const sales =
    data.data && "ticket" in data.data ? data.data : overview?.sales;
  const labels: Record<string, string> = {
    budget_income: "Receita orçada",
    actual_income: "Receita realizada",
    budget_expense: "Despesa orçada",
    actual_expense: "Despesa realizada",
  };
  const colors = ["#a5b4fc", "#6366f1", "#fda4af", "#e11d48"];
  const tooltip = <Tooltip content={(props) => <ChartTooltip {...props} />} />;
  return (
    <section className="space-y-4" aria-label="Inteligência operacional">
      <p className="text-xs text-slate-500">
        BI · mesmo período e origem. Filtros de descrição/status da tabela não
        alteram estes indicadores.
      </p>
      {data.isError && (
        <p role="alert" className="feedback-error">
          {errorMessage(data.error)}
        </p>
      )}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[
          ["Ticket médio", sales ? money(sales.ticket) : "—"],
          [
            "Margem de contribuição",
            sales?.margin ? `${sales.margin}%` : "Indisponível",
          ],
          [
            "Giro físico de estoque",
            overview?.turnover ? `${overview.turnover}x` : "—",
          ],
          [
            "Inadimplência em aberto",
            overview ? `${overview.delinquency}%` : "—",
          ],
        ].map(([name, value]) => (
          <article key={name} className="metric-card">
            <span className="card-subtitle">{name}</span>
            <strong className="block mt-4 text-2xl">{value}</strong>
          </article>
        ))}
      </div>
      <p className="text-xs text-slate-500">
        Margem depende de custos conhecidos (cobertura:{" "}
        {sales?.cost_coverage ?? "0"}%). Giro = unidades vendidas / estoque
        médio inicial e final. Inadimplência = recebíveis vencidos / recebíveis
        em aberto com vencimento no período.
      </p>
      {sales && (
        <div className="ui-card p-5">
          <div className="flex justify-between gap-3">
            <h2 className="card-title">Desempenho de vendas</h2>
            <select
              aria-label="Agrupar vendas"
              className="form-input !w-40"
              value={group}
              onChange={(e) => setGroup(e.target.value)}
            >
              <option value="categories">Categoria</option>
              <option value="sellers">Vendedor</option>
            </select>
          </div>
          <div className="h-64 mt-4">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                layout="vertical"
                data={(group === "categories"
                  ? sales.categories
                  : sales.sellers
                ).map((r) => ({ ...r, amount: Number(r.amount) }))}
              >
                <CartesianGrid
                  stroke="var(--chart-grid)"
                  strokeDasharray="3 3"
                  strokeOpacity={0.45}
                  horizontal={false}
                />
                <XAxis type="number" tick={{ fill: "var(--chart-text)" }} />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={120}
                  tick={{ fill: "var(--chart-text)", fontSize: 11 }}
                />
                {tooltip}
                <Bar
                  dataKey="amount"
                  name="Vendas"
                  fill="#818cf8"
                  radius={[0, 4, 4, 0]}
                  isAnimationActive={false}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
      {overview && (
        <div className="ui-card p-5">
          <div className="flex justify-between">
            <h2 className="card-title">Orçado vs. realizado</h2>
            {source === "real" &&
              user.permissions.includes("financeiro:lancamento:escrever") && (
                <button
                  className="btn-secondary"
                  onClick={() => setEditing(!editing)}
                >
                  Definir orçamento
                </button>
              )}
          </div>
          <p className="card-subtitle">
            Orçamento mensal proporcional aos dias selecionados. Realizado por
            data de caixa.
          </p>
          {editing && (
            <form
              className="grid gap-3 my-4 sm:grid-cols-4"
              onSubmit={(e) => {
                e.preventDefault();
                const d = Object.fromEntries(
                  new FormData(e.currentTarget),
                ) as Record<string, string>;
                const amount = parseMoney(d.amount ?? "");
                if (amount || /^0(?:[,.]0{1,2})?$/.test(d.amount ?? ""))
                  save.mutate({ ...d, amount: amount ?? "0.00" });
              }}
            >
              <input
                required
                name="month"
                type="month"
                aria-label="Competência orçamento"
                className="form-input"
              />
              <select
                name="category"
                aria-label="Categoria orçamento"
                className="form-input"
              >
                {categories.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
              <select
                name="kind"
                aria-label="Tipo orçamento"
                className="form-input"
              >
                <option value="receita">Receita</option>
                <option value="despesa">Despesa</option>
              </select>
              <input
                required
                name="amount"
                placeholder="Valor R$"
                aria-label="Valor orçamento"
                className="form-input"
              />
              <button disabled={save.isPending} className="btn-primary">
                Salvar orçamento
              </button>
              {save.isError && <p role="alert">{errorMessage(save.error)}</p>}
            </form>
          )}
          <div className="flex flex-wrap gap-4 py-4">
            {Object.entries(labels).map(([k, v]) => (
              <label key={k} className="text-xs flex gap-2">
                <input
                  type="checkbox"
                  checked={!!visible[k]}
                  onChange={() => setVisible((x) => ({ ...x, [k]: !x[k] }))}
                />
                {v}
              </label>
            ))}
          </div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart
                data={overview.budgets.map((row) =>
                  Object.fromEntries(
                    Object.entries(row).map(([k, v]) => [
                      k,
                      k === "month" ? v : Number(v),
                    ]),
                  ),
                )}
              >
                <defs>
                  {colors.map((color, i) => (
                    <linearGradient
                      key={i}
                      id={`${gradientId}-${i}`}
                      x1="0"
                      y1="0"
                      x2="0"
                      y2="1"
                    >
                      <stop offset="0%" stopColor={color} stopOpacity={0.22} />
                      <stop
                        offset="100%"
                        stopColor={color}
                        stopOpacity={0.01}
                      />
                    </linearGradient>
                  ))}
                </defs>
                <CartesianGrid
                  stroke="var(--chart-grid)"
                  strokeDasharray="3 3"
                  strokeOpacity={0.45}
                  vertical={false}
                />
                <XAxis dataKey="month" tick={{ fill: "var(--chart-text)" }} />
                <YAxis tick={{ fill: "var(--chart-text)" }} />
                {tooltip}
                {Object.keys(labels).map((k, i) => (
                  <Area
                    type="monotone"
                    strokeWidth={2.5}
                    key={k}
                    dataKey={k}
                    name={labels[k] ?? k}
                    hide={!visible[k]}
                    stroke={colors[i] ?? "#818cf8"}
                    fill={`url(#${gradientId}-${i})`}
                    isAnimationActive={false}
                  />
                ))}
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </section>
  );
}
