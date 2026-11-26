import { currentSource, replaceFilter } from "../../shared/lib/location";
import { ErrorBoundary } from "../../shared/components/ErrorBoundary";
import { useQuery } from "@tanstack/react-query";
import { request } from "../../shared/api/client";
import { BankingPage } from "../integration/BankingPage";
import { safeTime } from "../../shared/lib/dates";
import { Insights } from "../ecosystem/Insights";
import { ExportButtons } from "./components/ExportButtons";
import { lazy, Suspense, useEffect, useState } from "react";
import {
  ArrowDownLeft,
  ArrowUpRight,
  CalendarDays,
  CheckCircle2,
  Clock3,
  Plus,
  RefreshCw,
  Wallet,
  FlaskConical,
} from "lucide-react";
import { useCashSummary, useEntries } from "./api";
import { EntryTable } from "./components/EntryTable";
import { NewEntryModal } from "./components/NewEntryModal";
import { money, rangeDays, dateLabel } from "../../shared/lib/format";
import { errorMessage } from "../../shared/api/client";
import { useAuth } from "../identity/hooks/auth-store";
import type { Entry, Filters, Source } from "./types";
const CashCharts = lazy(() => import("./components/CashCharts"));
export function FinancePage({ overview = false }: { overview?: boolean }) {
  const [tab, setTab] = useState(() =>
    new URLSearchParams(location.search).get("tab") === "bank"
      ? "bank"
      : "cash",
  );
  const user = useAuth((s) => s.session!.user);
  return (
    <div className="space-y-6">
      {!overview &&
        user.permissions.includes("financeiro:conciliacao:executar") && (
          <nav className="flex gap-2" aria-label="Visão financeira">
            <button
              className={tab === "cash" ? "btn-primary" : "btn-secondary"}
              onClick={() => {
                replaceFilter("tab", "cash");
                setTab("cash");
              }}
            >
              Fluxo de caixa
            </button>
            <button
              className={tab === "bank" ? "btn-primary" : "btn-secondary"}
              onClick={() => {
                replaceFilter("tab", "bank");
                setTab("bank");
              }}
            >
              Conciliação bancária
            </button>
          </nav>
        )}
      <ErrorBoundary key={tab}>
        {tab === "bank" &&
        !overview &&
        user.permissions.includes("financeiro:conciliacao:executar") ? (
          <BankingPage />
        ) : (
          <FinanceContent overview={overview} />
        )}
      </ErrorBoundary>
    </div>
  );
}
function FinanceContent({ overview = false }: { overview?: boolean }) {
  const user = useAuth((s) => s.session!.user);
  const entryId = new URLSearchParams(location.search).get("lancamento");
  const linked = useQuery({
    queryKey: ["finance", user.tenant_id, user.user_id, "linked", entryId],
    queryFn: () => request<Entry>(`/financeiro/lancamentos/${entryId}`),
    enabled:
      !!entryId && user.permissions.includes("financeiro:lancamento:ler"),
  });
  const [filters, setFilters] = useState<Filters>({
    ...rangeDays(90),
    source: currentSource(),
    q: "",
    status: "",
    kind: "",
    category: "",
  });
  const [search, setSearch] = useState("");
  const [view, setView] = useState<"chart" | "grid">("chart");
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(10);
  const [modal, setModal] = useState(false);
  const [notice, setNotice] = useState("");
  const [periodError, setPeriodError] = useState("");
  const [customStart, setCustomStart] = useState(filters.start_date);
  const [customEnd, setCustomEnd] = useState(filters.end_date);
  const summary = useCashSummary(filters);
  const entries = useEntries(filters, page, size);
  const canWrite = user.permissions.includes("financeiro:lancamento:escrever");
  useEffect(() => {
    const timer = setTimeout(() => {
      setFilters((f) => (f.q === search ? f : { ...f, q: search }));
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 6000);
    return () => clearTimeout(timer);
  }, [notice]);
  const changeFilter = (key: "kind" | "status" | "category", value: string) => {
    setFilters((f) => ({ ...f, [key]: value }));
    setPage(1);
  };
  function source(value: Source) {
    replaceFilter("source", value);
    setFilters((f) => ({ ...f, source: value }));
    setPage(1);
  }
  function period(days: number) {
    const range = rangeDays(days);
    setFilters((f) => ({ ...f, ...range }));
    setCustomStart(range.start_date);
    setCustomEnd(range.end_date);
    setPeriodError("");
    setPage(1);
  }
  function customPeriod() {
    const difference =
      (Date.parse(customEnd) - Date.parse(customStart)) / 86400000;
    if (!Number.isFinite(difference) || difference < 0 || difference > 365) {
      setPeriodError("Selecione de 1 a 366 dias, em ordem crescente.");
      return;
    }
    setPeriodError("");
    setFilters((f) => ({ ...f, start_date: customStart, end_date: customEnd }));
    setPage(1);
  }
  function created(entry: Entry) {
    const range = rangeDays(90); // Include a newly created future/historical entry immediately.
    const start =
      entry.effective_on < range.start_date
        ? entry.effective_on
        : range.start_date;
    const end =
      entry.effective_on > range.end_date ? entry.effective_on : range.end_date;
    const bounded =
      (Date.parse(end) - Date.parse(start)) / 86400000 <= 365
        ? { start_date: start, end_date: end }
        : { start_date: entry.effective_on, end_date: entry.effective_on };
    setFilters({
      ...bounded,
      source: "real",
      q: "",
      status: "",
      kind: "",
      category: "",
    });
    setCustomStart(bounded.start_date);
    setCustomEnd(bounded.end_date);
    setSearch("");
    setPage(1);
    setModal(false);
    setNotice(
      "Lançamento salvo. Você está visualizando as movimentações reais.",
    );
  }
  const stats = summary.isError ? undefined : summary.data;
  return (
    <div className="page-enter space-y-6">
      {linked.isError && <p role="alert">{errorMessage(linked.error)}</p>}
      {linked.data && (
        <section className="ui-card space-y-2 p-5">
          <h2 className="font-semibold">Lançamento do pedido</h2>
          <p>
            {linked.data.description} · {linked.data.counterparty} ·{" "}
            {money(linked.data.amount)}
          </p>
          <p>
            {linked.data.status === "concluido" ? "Liquidado" : "Em aberto"} ·{" "}
            {dateLabel(linked.data.effective_on)}
          </p>
          {user.permissions.includes("financeiro:conciliacao:executar") && (
            <a
              className="btn-secondary"
              href="/app/financeiro?source=real&tab=bank"
            >
              Abrir conciliação
            </a>
          )}
        </section>
      )}

      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="mb-2 flex items-center gap-2 text-[10px] font-medium uppercase tracking-[.14em] text-slate-400">
            <span className="h-1.5 w-1.5 rounded-full bg-indigo-400" />
            Workspace financeiro
          </div>
          <h1 className="page-title">
            {overview ? "Visão geral" : "Fluxo de caixa"}
          </h1>
          <p className="mt-2 text-xs text-slate-500">
            {overview
              ? `Bem-vindo, ${user.display_name.split(" ")[0]}. Acompanhe sua operação em um só lugar.`
              : "Controle receitas, despesas e compromissos com clareza."}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            className="btn-secondary"
            onClick={() => {
              void summary.refetch();
              void entries.refetch();
            }}
            disabled={summary.isFetching || entries.isFetching}
          >
            <RefreshCw
              size={14}
              className={summary.isFetching ? "animate-spin" : ""}
            />
            <span className="hidden sm:inline">Atualizar</span>
          </button>
          {canWrite && (
            <button className="btn-primary" onClick={() => setModal(true)}>
              <Plus size={16} />
              Novo lançamento
            </button>
          )}
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="segmented source-tabs">
          <button
            className={filters.source === "demo" ? "selected" : ""}
            onClick={() => source("demo")}
          >
            <FlaskConical size={13} />
            Demonstração
          </button>
          <button
            className={filters.source === "real" ? "selected" : ""}
            onClick={() => source("real")}
          >
            <Wallet size={13} />
            Movimentações reais
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="segmented">
            {[7, 30, 90].map((days) => (
              <button key={days} onClick={() => period(days)}>
                {days} dias
              </button>
            ))}
          </div>
          <details className="period-popover">
            <summary className="btn-secondary">
              <CalendarDays size={14} />
              {dateLabel(filters.start_date)} – {dateLabel(filters.end_date)}
            </summary>
            <div className="period-panel">
              <label className="field-label" htmlFor="range-start">
                De
              </label>
              <input
                id="range-start"
                className="form-input"
                type="date"
                value={customStart}
                onChange={(e) => setCustomStart(e.target.value)}
              />
              <label className="field-label mt-3" htmlFor="range-end">
                Até
              </label>
              <input
                id="range-end"
                className="form-input"
                type="date"
                value={customEnd}
                onChange={(e) => setCustomEnd(e.target.value)}
              />
              {periodError && (
                <p role="alert" className="mt-2 text-xs text-red-600">
                  {periodError}
                </p>
              )}
              <button
                className="btn-primary mt-3 w-full"
                onClick={customPeriod}
              >
                Aplicar período
              </button>
            </div>
          </details>
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="segmented">
          <button
            className={view === "chart" ? "selected" : ""}
            onClick={() => setView("chart")}
          >
            Visão gráfica
          </button>
          <button
            className={view === "grid" ? "selected" : ""}
            onClick={() => setView("grid")}
          >
            Visão em planilha
          </button>
        </div>
        <ExportButtons filters={filters} />
      </div>
      {filters.source === "demo" && (
        <div className="demo-strip">
          <FlaskConical size={15} />
          <p>
            <strong>Dados demonstrativos</strong>
            <span className="hidden sm:inline">
              {" "}
              · Série sintética, separada das movimentações reais.
            </span>
          </p>
          <span className="ml-auto text-[10px]">
            {stats?.total_records ?? "—"} no filtro
          </span>
        </div>
      )}
      {notice && (
        <div
          className="flex items-center gap-2 rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-xs text-emerald-700"
          role="status"
        >
          <CheckCircle2 size={16} />
          {notice}
        </div>
      )}
      {summary.isError && (
        <div className="feedback-error" role="alert">
          {errorMessage(summary.error)}
        </div>
      )}
      <section
        className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"
        aria-label="Indicadores do período"
      >
        {[
          {
            label: "Receitas realizadas",
            value: stats?.income,
            icon: ArrowDownLeft,
            cls: "text-emerald-600 bg-emerald-50",
            helper: "Recebimentos concluídos",
          },
          {
            label: "Despesas realizadas",
            value: stats?.expense,
            icon: ArrowUpRight,
            cls: "text-rose-500 bg-rose-50",
            helper: "Pagamentos concluídos",
          },
          {
            label: "Resultado no período",
            value: stats?.net,
            icon: Wallet,
            cls: "text-indigo-600 bg-indigo-50",
            helper: "Recebido menos pago · sem saldo inicial",
          },
          {
            label: "A receber",
            value: stats?.pending_income,
            icon: Clock3,
            cls: "text-amber-600 bg-amber-50",
            helper: `A pagar: ${stats ? money(stats.pending_expense) : "—"}`,
          },
        ].map((card) => (
          <article className="metric-card" key={card.label}>
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-medium text-slate-500">
                {card.label}
              </span>
              <span
                className={`grid h-8 w-8 place-items-center rounded-lg ${card.cls}`}
              >
                <card.icon size={16} />
              </span>
            </div>
            <strong className="mt-5 block text-[26px] font-semibold tracking-[-.045em] tabular-nums text-slate-900">
              {card.value !== undefined ? money(card.value) : "—"}
            </strong>
            <p className="mt-3 text-[10px] text-slate-400">{card.helper}</p>
          </article>
        ))}
      </section>
      {view === "chart" &&
        (stats ? (
          <Suspense fallback={<div className="chart-skeleton" />}>
            <CashCharts summary={stats} />
          </Suspense>
        ) : (
          !summary.isError && (
            <div
              className="chart-skeleton"
              role="status"
              aria-label="Carregando gráficos"
            />
          )
        ))}
      <Insights
        source={filters.source}
        start={filters.start_date}
        end={filters.end_date}
      />
      {entries.isError ? (
        <div className="feedback-error" role="alert">
          {errorMessage(entries.error)}{" "}
          <button onClick={() => void entries.refetch()} className="underline">
            Tentar novamente
          </button>
        </div>
      ) : (
        <EntryTable
          key={`${page}:${size}:${JSON.stringify(filters)}`}
          onSort={(key) => {
            setFilters((f) => ({
              ...f,
              sort: key,
              desc: f.sort === key && f.desc !== "false" ? "false" : "true",
            }));
            setPage(1);
          }}
          data={entries.data}
          filters={filters}
          onFilter={changeFilter}
          search={search}
          onSearch={setSearch}
          page={page}
          onPage={setPage}
          size={size}
          onSize={(value) => {
            setSize(value);
            setPage(1);
          }}
          loading={entries.isFetching}
        />
      )}
      <p className="text-right text-[10px] text-slate-400">
        {summary.dataUpdatedAt
          ? `Atualizado às ${safeTime(summary.dataUpdatedAt)}`
          : ""}{" "}
        · Valores em reais (BRL)
      </p>
      {modal && (
        <NewEntryModal onClose={() => setModal(false)} onCreated={created} />
      )}
    </div>
  );
}
