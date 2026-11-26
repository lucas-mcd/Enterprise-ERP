import type { ReactNode } from "react";
import { ArrowDownUp, ChevronLeft, ChevronRight } from "lucide-react";
export type Column<T> = {
  key: string;
  label: string;
  render: (row: T) => ReactNode;
  sortable?: boolean;
};
export function DataGrid<T extends { id: string }>({
  columns,
  rows,
  total,
  page,
  size,
  sort,
  desc,
  onSort,
  onPage,
  loading,
}: {
  columns: Column<T>[];
  rows: T[];
  total: number;
  page: number;
  size: number;
  sort: string;
  desc: boolean;
  onSort: (key: string) => void;
  onPage: (page: number) => void;
  loading: boolean;
}) {
  return (
    <section className="ui-card overflow-hidden" aria-busy={loading}>
      <div className="overflow-x-auto">
        <table className="cash-table">
          <thead>
            <tr>
              {columns.map((c) => (
                <th
                  key={c.key}
                  aria-sort={
                    c.key === sort
                      ? desc
                        ? "descending"
                        : "ascending"
                      : undefined
                  }
                >
                  {c.sortable ? (
                    <button
                      onClick={() => onSort(c.key)}
                      className="flex items-center gap-2"
                    >
                      {c.label}
                      <ArrowDownUp size={12} />
                    </button>
                  ) : (
                    c.label
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                {columns.map((c) => (
                  <td key={c.key}>{c.render(row)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length && (
          <p className="p-10 text-center text-sm text-slate-500">
            {loading ? "Carregando…" : "Nenhum registro para estes filtros."}
          </p>
        )}
      </div>
      <footer className="flex items-center justify-between border-t border-slate-200 p-4 text-xs text-slate-500">
        <span>
          {total} registros · Página {page} de{" "}
          {Math.max(1, Math.ceil(total / size))}
        </span>
        <div className="flex gap-2">
          <button
            className="icon-button"
            aria-label="Página anterior"
            disabled={loading || page === 1}
            onClick={() => onPage(page - 1)}
          >
            <ChevronLeft size={16} />
          </button>
          <button
            className="icon-button"
            aria-label="Próxima página"
            disabled={loading || page * size >= total}
            onClick={() => onPage(page + 1)}
          >
            <ChevronRight size={16} />
          </button>
        </div>
      </footer>
    </section>
  );
}
