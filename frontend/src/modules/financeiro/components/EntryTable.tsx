import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { request, errorMessage } from "../../../shared/api/client";
import { useAuth } from "../../identity/hooks/auth-store";
import { download } from "./ExportButtons";
import { isoToday } from "../../../shared/lib/format";
import {
  ArrowDownLeft,
  ArrowUpRight,
  ChevronLeft,
  ChevronRight,
  Search,
  SlidersHorizontal,
  LoaderCircle,
  Inbox,
} from "lucide-react";
import { categories } from "../types";
import type { EntryPage, Filters } from "../types";
import { money, dateLabel } from "../../../shared/lib/format";
export function EntryTable({
  onSort,
  data,
  filters,
  onFilter,
  search,
  onSearch,
  page,
  onPage,
  size,
  onSize,
  loading,
}: {
  onSort?: (key: string) => void;
  data: EntryPage | undefined;
  filters: Filters;
  onFilter: (key: "kind" | "status" | "category", value: string) => void;
  search: string;
  onSearch: (value: string) => void;
  page: number;
  onPage: (value: number) => void;
  size: number;
  onSize: (value: number) => void;
  loading: boolean;
}) {
  const [selected, setSelected] = useState<string[]>([]),
    [date, setDate] = useState(isoToday());
  const user = useAuth((s) => s.session!.user),
    client = useQueryClient();
  const rows = (data?.items ?? []).filter((r) => selected.includes(r.id));
  const canWrite = user.permissions.includes("financeiro:lancamento:escrever");
  const action = useMutation({
    mutationFn: async ({ kind, id }: { kind: string; id?: string }) => {
      const body = {
        rows: rows.map((r) => ({ id: r.id, version: r.version })),
        settled_on: date,
      };
      if (kind === "csv" || kind === "xlsx")
        return download("/financeiro/lotes/exportar", `selecionados.${kind}`, {
          ...body,
          format: kind,
        });
      await request(
        kind === "approve"
          ? `/governanca/aprovar/cash/${id}`
          : "/financeiro/lotes/baixar",
        {
          method: "POST",
          ...(kind === "approve" ? {} : { body: JSON.stringify(body) }),
        },
      );
    },
    onSuccess: () => {
      setSelected([]);
      void client.invalidateQueries({ queryKey: ["finance"] });
      void client.invalidateQueries({ queryKey: ["bi"] });
    },
  });
  const pages = Math.max(1, Math.ceil((data?.total ?? 0) / size));
  return (
    <section
      className="ui-card overflow-hidden"
      aria-label="Lançamentos de caixa"
      aria-busy={loading}
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
        <div className="flex items-center gap-2">
          <h2 className="card-title">Lançamentos</h2>
          <span className="count-pill">{data?.total ?? "—"}</span>
          {loading && (
            <LoaderCircle size={13} className="animate-spin text-slate-400" />
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <label className="select-control">
            <select
              aria-label="Filtrar por categoria"
              value={filters.category}
              onChange={(e) => onFilter("category", e.target.value)}
            >
              <option value="">Todas as categorias</option>
              {categories.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
          <label className="search-control">
            <Search size={14} />
            <input
              aria-label="Buscar lançamentos"
              placeholder="Buscar descrição ou contraparte…"
              value={search}
              onChange={(e) => onSearch(e.target.value)}
              maxLength={100}
            />
          </label>
          <label className="select-control">
            <SlidersHorizontal size={13} />
            <select
              aria-label="Filtrar por status"
              value={filters.status}
              onChange={(e) => onFilter("status", e.target.value)}
            >
              <option value="">Todos os status</option>
              <option value="aguardando_aprovacao">Aguardando Aprovação</option>
              <option value="pendente">Pendente</option>
              <option value="concluido">Concluído</option>
            </select>
          </label>
          <label className="select-control">
            <select
              aria-label="Filtrar por tipo"
              value={filters.kind}
              onChange={(e) => onFilter("kind", e.target.value)}
            >
              <option value="">Receitas e despesas</option>
              <option value="receita">Receitas</option>
              <option value="despesa">Despesas</option>
            </select>
          </label>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 p-4 text-xs">
        <label className="flex gap-2">
          <input
            type="checkbox"
            aria-label="Selecionar página"
            checked={!!data?.items.length && rows.length === data.items.length}
            onChange={(e) =>
              setSelected(
                e.target.checked ? (data?.items ?? []).map((r) => r.id) : [],
              )
            }
          />
          Selecionar página ({rows.length})
        </label>
        {canWrite && filters.source === "real" && (
          <>
            <input
              aria-label="Data da baixa"
              className="form-input !w-40"
              type="date"
              value={date}
              max={isoToday()}
              onChange={(e) => setDate(e.target.value)}
            />
            <button
              className="btn-secondary"
              disabled={!rows.length || action.isPending}
              onClick={() => action.mutate({ kind: "settle" })}
            >
              Baixar pagos / recebidos
            </button>
          </>
        )}
        {user.permissions.includes("financeiro:relatorio:ler") &&
          ["csv", "xlsx"].map((kind) => (
            <button
              key={kind}
              className="btn-secondary"
              disabled={!rows.length || action.isPending}
              onClick={() => action.mutate({ kind })}
            >
              Selecionados {kind.toUpperCase()}
            </button>
          ))}
        {action.isError && (
          <p role="alert" className="feedback-error">
            {errorMessage(action.error)}
          </p>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="cash-table">
          <caption className="sr-only">
            Lançamentos paginados e filtrados pela data de caixa
          </caption>
          <thead>
            <tr>
              <th>Selecionar</th>
              <th
                aria-sort={
                  filters.sort === "description"
                    ? filters.desc === "false"
                      ? "ascending"
                      : "descending"
                    : undefined
                }
              >
                <button onClick={() => onSort?.("description")}>
                  Descrição / contraparte ↕
                </button>
              </th>
              <th
                aria-sort={
                  filters.sort === "category"
                    ? filters.desc === "false"
                      ? "ascending"
                      : "descending"
                    : undefined
                }
              >
                <button onClick={() => onSort?.("category")}>
                  Categoria ↕
                </button>
              </th>
              <th
                aria-sort={
                  filters.sort === "effective_on"
                    ? filters.desc === "false"
                      ? "ascending"
                      : "descending"
                    : undefined
                }
              >
                <button onClick={() => onSort?.("effective_on")}>
                  Data de caixa ↕
                </button>
              </th>
              <th
                aria-sort={
                  filters.sort === "status"
                    ? filters.desc === "false"
                      ? "ascending"
                      : "descending"
                    : undefined
                }
              >
                <button onClick={() => onSort?.("status")}>Status ↕</button>
              </th>
              <th className="!text-right">
                <button onClick={() => onSort?.("amount")}>Valor ↕</button>
              </th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((entry) => (
              <tr key={entry.id}>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`Selecionar ${entry.description}`}
                    checked={selected.includes(entry.id)}
                    onChange={(e) =>
                      setSelected((v) =>
                        e.target.checked
                          ? [...v, entry.id]
                          : v.filter((id) => id !== entry.id),
                      )
                    }
                  />
                </td>
                <td>
                  <div className="flex items-center gap-3">
                    <span
                      className={`transaction-icon ${entry.kind === "receita" ? "income" : "expense"}`}
                    >
                      {entry.kind === "receita" ? (
                        <ArrowDownLeft size={16} />
                      ) : (
                        <ArrowUpRight size={16} />
                      )}
                    </span>
                    <div>
                      <span
                        className="block max-w-[300px] truncate font-medium text-slate-700"
                        title={entry.description}
                      >
                        {entry.description}
                      </span>
                      <span className="mt-1 block text-[10px] text-slate-400">
                        {entry.counterparty || "Sem contraparte"}
                        {entry.is_simulated ? " · Simulação" : ""}
                      </span>
                    </div>
                  </div>
                </td>
                <td>
                  <span className="category-chip">{entry.category}</span>
                </td>
                <td>
                  <span className="text-slate-600">
                    {dateLabel(entry.effective_on)}
                  </span>
                  <span className="mt-0.5 block text-[9px] text-slate-400">
                    {entry.status === "concluido" ? "Liquidação" : "Vencimento"}
                  </span>
                </td>
                <td>
                  <span className={`status-badge ${entry.status}`}>
                    <i />
                    {entry.status === "concluido"
                      ? "Concluído"
                      : entry.status === "aguardando_aprovacao"
                        ? "Aguardando Aprovação"
                        : "Pendente"}
                  </span>
                  {entry.status === "aguardando_aprovacao" &&
                    !entry.is_simulated &&
                    canWrite && (
                      <button
                        className="btn-secondary ml-2"
                        disabled={action.isPending}
                        onClick={() =>
                          action.mutate({ kind: "approve", id: entry.id })
                        }
                      >
                        Aprovar
                      </button>
                    )}
                </td>
                <td
                  className={`!text-right font-medium tabular-nums ${entry.kind === "receita" ? "text-emerald-600" : "text-slate-700"}`}
                >
                  <span className="sr-only">
                    {entry.kind === "receita" ? "Receita" : "Despesa"}
                  </span>
                  {entry.kind === "receita" ? "+ " : "− "}
                  {money(entry.amount)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!data?.items.length && (
          <div className="flex min-h-40 flex-col items-center justify-center gap-2 p-6 text-center">
            <Inbox size={24} className="text-slate-300" />
            <p className="text-xs text-slate-500">
              {loading
                ? "Buscando lançamentos…"
                : "Nenhum lançamento para estes filtros."}
            </p>
          </div>
        )}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 px-5 py-3 text-[11px] text-slate-500">
        <span>
          {data?.total
            ? `${Math.min((page - 1) * size + 1, data.total)}–${Math.min(page * size, data.total)} de ${data.total} lançamentos`
            : "0 lançamentos"}
        </span>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2">
            Por página
            <select
              className="rounded-md border border-slate-200 bg-white px-2 py-1"
              value={size}
              aria-label="Lançamentos por página"
              onChange={(e) => onSize(Number(e.target.value))}
            >
              <option value={10}>10</option>
              <option value={20}>20</option>
              <option value={50}>50</option>
            </select>
          </label>
          <button
            className="icon-button border border-slate-200"
            aria-label="Página anterior"
            disabled={page <= 1 || loading}
            onClick={() => onPage(page - 1)}
          >
            <ChevronLeft size={14} />
          </button>
          <span>
            Página {page} de {pages}
          </span>
          <button
            className="icon-button border border-slate-200"
            aria-label="Próxima página"
            disabled={page >= pages || loading}
            onClick={() => onPage(page + 1)}
          >
            <ChevronRight size={14} />
          </button>
        </div>
      </div>
    </section>
  );
}
