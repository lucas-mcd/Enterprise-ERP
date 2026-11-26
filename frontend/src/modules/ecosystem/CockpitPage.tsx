import { currentSource, replaceFilter } from "../../shared/lib/location";
import { ErrorBoundary } from "../../shared/components/ErrorBoundary";
import { safeDateTime, safeTime } from "../../shared/lib/dates";
import { lazy, Suspense, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowUpRight,
  Boxes,
  BriefcaseBusiness,
  Wallet,
  ShieldCheck,
  RefreshCw,
} from "lucide-react";
import { request, errorMessage } from "../../shared/api/client";
import { useAuth } from "../identity/hooks/auth-store";
import { money } from "../../shared/lib/format";
import type { Summary } from "../financeiro/types";
const CashCharts = lazy(() => import("../financeiro/components/CashCharts"));
type Cockpit = {
  start: string;
  end: string;
  updated_at: string;
  sales: {
    revenue: string;
    top_products: { name: string; quantity: number; amount: string }[];
  } | null;
  cash: Summary | null;
  stock: {
    critical: number;
    items: { name: string; balance: number; minimum: number }[];
  } | null;
  purchases: {
    waiting: number;
    items: { name: string; amount: string }[];
  } | null;
  approvals: { count: number; scopes: string[] } | null;
  fiscal: Record<string, string> | null;
  people: { department: string; count: number }[] | null;
  audit:
    | {
        id: string;
        table: string;
        operation: string;
        date: string;
        actor_id: string | null;
      }[]
    | null;
  projects: Record<string, number> | null;
  assets: { count: number; cost: string } | null;
};
function go(path: string) {
  history.pushState({}, "", `/app/${path}`);
  window.dispatchEvent(new PopStateEvent("popstate"));
}
export function CockpitPage() {
  const tenantId = useAuth((state) => state.session?.user.tenant_id);
  return (
    <ErrorBoundary
      title="Não foi possível renderizar a visão geral"
      resetKeys={[tenantId]}
    >
      <CockpitContent />
    </ErrorBoundary>
  );
}
function CockpitContent() {
  const user = useAuth((s) => s.session!.user),
    [source, setSource] = useState<string>(currentSource);
  const query = useQuery({
    queryKey: ["cockpit", user.tenant_id, user.user_id, source],
    queryFn: ({ signal }) =>
      request<Cockpit>(`/cockpit?source=${source}`, { signal }),
    refetchInterval: 15000,
    retry: false,
  });
  const d = query.data;
  return (
    <div className="space-y-6 page-enter">
      <header className="cockpit-hero flex flex-wrap items-center justify-between gap-4 rounded-2xl py-5">
        <div>
          <p className="mb-2 text-[10px] uppercase tracking-[.2em] text-indigo-500">
            EXECUTIVE WORKSPACE · 360°
          </p>
          <h1 className="page-title">O pulso da sua empresa.</h1>
          <p className="mt-2 text-xs text-slate-500">
            Olá, {user.display_name.split(" ")[0]}. Operação conectada, decisões
            com contexto.
          </p>
        </div>
        <div className="flex gap-2">
          <select
            aria-label="Origem do cockpit"
            className="form-input !w-40"
            value={source}
            onChange={(e) => {
              replaceFilter("source", e.target.value);
              setSource(e.target.value);
            }}
          >
            <option value="demo">Demonstração</option>
            <option value="real">Operação real</option>
          </select>
          <button
            className="icon-button"
            aria-label="Atualizar cockpit"
            disabled={query.isFetching}
            onClick={() => void query.refetch()}
          >
            <RefreshCw
              size={17}
              className={query.isFetching ? "animate-spin" : ""}
            />
          </button>
        </div>
      </header>
      <p className="text-xs text-slate-500">
        Mês corrente · {d?.start ?? "…"} a {d?.end ?? "…"}. Estoque, pessoas e
        aprovações: posição atual. Atualização a cada 15 segundos.
      </p>
      {source === "demo" && (
        <p className="demo-strip">
          Ambiente demonstrativo · dados sintéticos separados da operação real.
        </p>
      )}
      {query.isError && (
        <p className="feedback-error" role="alert">
          {errorMessage(query.error)}
        </p>
      )}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[
          {
            label: "Faturamento comercial",
            value: d?.sales ? money(d.sales.revenue) : "—",
            helper: "Pedidos de venda concluídos no mês",
            icon: ArrowUpRight,
          },
          {
            label: "Saldo líquido em caixa",
            value: d?.cash ? money(d.cash.net) : "—",
            helper: "Entradas − saídas no mês; sem saldo inicial",
            icon: Wallet,
          },
          {
            label: "Itens em estoque crítico",
            value: d?.stock?.critical ?? "—",
            helper: "Produtos com saldo ≤ mínimo",
            icon: Boxes,
          },
          {
            label: "Pendências de aprovação",
            value: d?.approvals?.count ?? "—",
            helper:
              d?.approvals?.scopes.join(" + ") ?? "Conforme suas permissões",
            icon: ShieldCheck,
          },
        ].map((k) => (
          <article key={k.label} className="metric-card">
            <div className="flex justify-between">
              <span className="text-xs text-slate-500">{k.label}</span>
              <k.icon size={17} className="text-indigo-400" />
            </div>
            <strong className="block mt-6 text-3xl font-semibold tracking-tight">
              {k.value}
            </strong>
            <p className="mt-3 text-[10px] text-slate-500">{k.helper}</p>
          </article>
        ))}
      </div>
      {d?.cash && (
        <Suspense fallback={<div className="chart-skeleton" />}>
          <CashCharts summary={d.cash} />
        </Suspense>
      )}
      <div className="grid gap-5 lg:grid-cols-2 xl:grid-cols-3">
        {d?.sales && (
          <Widget
            title="Comercial & vendas"
            subtitle="Top produtos · faturamento do mês"
            onOpen={() => go("vendas")}
          >
            {d.sales.top_products.length ? (
              d.sales.top_products.map((r, i) => (
                <div className="cockpit-row" key={r.name + i}>
                  <span className="text-indigo-400">0{i + 1}</span>
                  <div className="min-w-0 flex-1">
                    <strong className="block truncate">{r.name}</strong>
                    <small className="text-slate-500">
                      {r.quantity} unidades
                    </small>
                  </div>
                  <strong>{money(r.amount)}</strong>
                </div>
              ))
            ) : (
              <Empty />
            )}
          </Widget>
        )}
        {d?.stock && (
          <Widget
            title="Reposição de estoque"
            subtitle="Prioridades do almoxarifado"
            onOpen={() => go("estoque")}
          >
            {d.stock.items.length ? (
              d.stock.items.map((r) => (
                <div className="cockpit-row" key={r.name}>
                  <span className="h-2 w-2 rounded-full bg-amber-400" />
                  <strong className="flex-1">{r.name}</strong>
                  <span className="text-amber-600">
                    {r.balance} / mín. {r.minimum}
                  </span>
                </div>
              ))
            ) : (
              <Empty text="Nenhum item abaixo do mínimo." />
            )}
          </Widget>
        )}
        {d?.purchases && (
          <Widget
            title="Suprimentos"
            subtitle={`${d.purchases.waiting} compras aguardando alçada`}
            onOpen={() => go("compras")}
          >
            {d.purchases.items.length ? (
              d.purchases.items.map((r, i) => (
                <div className="cockpit-row" key={i}>
                  <span className="flex-1">{r.name}</span>
                  <strong>{money(r.amount)}</strong>
                </div>
              ))
            ) : (
              <Empty text="Nenhuma compra aguardando aprovação." />
            )}
          </Widget>
        )}
        {d?.fiscal && (
          <Widget
            title="Fiscal"
            subtitle="Impostos simulados · notas autorizadas criadas no mês"
            onOpen={() => go("fiscal")}
          >
            {Object.entries(d.fiscal).map(([k, v]) => (
              <div className="cockpit-row" key={k}>
                <span className="flex-1 text-slate-500">{k}</span>
                <strong>{money(v)}</strong>
              </div>
            ))}
          </Widget>
        )}
        {d?.people && (
          <Widget
            title="Pessoas & estrutura"
            subtitle={`${d.people.reduce((n, r) => n + r.count, 0)} colaboradores ativos`}
            onOpen={() => go("rh")}
          >
            {d.people.length ? (
              d.people.map((r) => (
                <div className="cockpit-row" key={r.department}>
                  <span className="flex-1">{r.department}</span>
                  <span className="count-pill">{r.count}</span>
                </div>
              ))
            ) : (
              <Empty />
            )}
          </Widget>
        )}
        {d?.projects && (
          <Widget
            title="Projetos & operações"
            subtitle="Portfólio em andamento"
            onOpen={() => go("projetos")}
          >
            {Object.entries(d.projects).map(([k, v]) => (
              <div className="cockpit-row" key={k}>
                <BriefcaseBusiness size={14} className="text-indigo-400" />
                <span className="flex-1">
                  {
                    (
                      {
                        planejamento: "Planejamento",
                        em_execucao: "Em execução",
                        concluido: "Concluído",
                      } as Record<string, string>
                    )[k]
                  }
                </span>
                <strong>{v}</strong>
              </div>
            ))}
          </Widget>
        )}
        {d?.assets && (
          <Widget
            title="Patrimônio"
            subtitle="Bens ativos cadastrados"
            onOpen={() => go("ativos")}
          >
            <div className="cockpit-row">
              <span className="flex-1">Bens</span>
              <strong>{d.assets.count}</strong>
            </div>
            <div className="cockpit-row">
              <span className="flex-1">Custo de aquisição</span>
              <strong>{money(d.assets.cost)}</strong>
            </div>
            <p className="mt-3 text-xs text-slate-500">
              Consulte a depreciação e os responsáveis no módulo.
            </p>
          </Widget>
        )}
        {d?.audit && (
          <Widget
            title="Governança em tempo real"
            subtitle="Últimas 5 ações críticas · todas as origens do tenant"
            onOpen={() => go("auditoria")}
          >
            {d.audit.map((r) => (
              <div key={r.id} className="cockpit-row">
                <span className="h-2 w-2 rounded-full bg-indigo-400" />
                <div className="flex-1">
                  <strong>
                    {r.operation} · {r.table}
                  </strong>
                  <small className="block text-slate-500">
                    {safeDateTime(r.date)}
                  </small>
                </div>
              </div>
            ))}
          </Widget>
        )}
      </div>
      <p className="text-right text-[10px] text-slate-400">
        {d
          ? `Atualizado às ${safeTime(d.updated_at)}`
          : "Carregando indicadores…"}{" "}
        · Setores restritos não são consultados nem exibidos.
      </p>
    </div>
  );
}
function Empty({ text = "Sem registros neste recorte." }: { text?: string }) {
  return <p className="py-8 text-xs text-slate-500">{text}</p>;
}
function Widget({
  title,
  subtitle,
  onOpen,
  children,
}: {
  title: string;
  subtitle: string;
  onOpen: () => void;
  children: React.ReactNode;
}) {
  return (
    <ErrorBoundary title="Não foi possível renderizar este widget">
      <section className="ui-card cockpit-widget p-5">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 className="card-title">{title}</h2>
            <p className="card-subtitle">{subtitle}</p>
          </div>
          <button
            className="icon-button"
            aria-label={`Abrir ${title}`}
            onClick={onOpen}
          >
            <ArrowUpRight size={16} />
          </button>
        </div>
        {children}
      </section>
    </ErrorBoundary>
  );
}
