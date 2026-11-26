import type { components } from "../../../shared/api/generated";
import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Download, FileText, LoaderCircle } from "lucide-react";
import {
  request,
  authenticatedFetch,
  ApiError,
  errorMessage,
} from "../../../shared/api/client";
import { useAuth } from "../../identity/hooks/auth-store";
import { queryString } from "../api";
import type { Filters } from "../types";
type Job = {
  id: string;
  status: "queued" | "ready" | "failed";
  error: string | null;
};
export async function download(path: string, name: string, body?: unknown) {
  const response = await authenticatedFetch(`/api/v1${path}`, {
    method: body ? "POST" : "GET",
    body: body ? JSON.stringify(body) : null,
  });
  if (!response.ok) {
    throw new ApiError(
      response.status,
      response.status === 410
        ? "Relatório expirado. Gere novamente."
        : response.status === 409
          ? "Reduza os filtros: máximo de 5.000 registros."
          : "Não foi possível baixar o arquivo. Confira sua sessão e permissões.",
    );
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function ExportButtons({ filters }: { filters: Filters }) {
  const user = useAuth((s) => s.session!.user);
  const [id, setId] = useState<string | null>(null);
  const [started, setStarted] = useState(0);
  const [open, setOpen] = useState(false);
  const history = useQuery({
    queryKey: ["reports", user.tenant_id, user.user_id],
    queryFn: () =>
      request<components["schemas"]["ReportSummary"][]>(
        "/financeiro/exportacoes",
      ),
    enabled: open && user.permissions.includes("financeiro:relatorio:ler"),
    refetchInterval: (q) =>
      q.state.data?.some((row) => row.status === "queued") ? 3000 : false,
  });
  const job = useQuery({
    queryKey: ["report", user.tenant_id, user.user_id, id],
    queryFn: () => request<Job>(`/financeiro/exportacoes/${id}`),
    enabled: !!id,
    retry: false,
    refetchInterval: (q) =>
      q.state.data?.status === "queued" && Date.now() - started < 600000
        ? 2000
        : false,
  });
  const create = useMutation({
    mutationFn: () =>
      request<Job>(`/financeiro/exportacoes/pdf?${queryString(filters)}`, {
        method: "POST",
      }),
    onSuccess: (r) => {
      setStarted(Date.now());
      setId(r.id);
      if (open) void history.refetch();
    },
  });
  const file = useMutation({
    mutationFn: ({ path, name }: { path: string; name: string }) =>
      download(path, name),
  });
  if (!user.permissions.includes("financeiro:relatorio:ler")) return null;
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        {["csv", "xlsx"].map((format) => (
          <button
            key={format}
            className="btn-secondary"
            disabled={file.isPending}
            onClick={() =>
              file.mutate({
                path: `/financeiro/exportacoes/planilha?${queryString(filters)}&format=${format}`,
                name: `fluxo-caixa.${format}`,
              })
            }
          >
            <Download size={14} />
            {format.toUpperCase()}
          </button>
        ))}
        <button
          className="btn-secondary"
          disabled={create.isPending || job.data?.status === "queued"}
          onClick={() => create.mutate()}
        >
          <FileText size={14} />
          Exportar relatório PDF
        </button>
        {job.data?.status === "queued" && (
          <span
            className="flex items-center gap-2 text-xs text-indigo-500"
            role="status"
          >
            <LoaderCircle size={14} className="animate-spin" />
            Relatório na fila de processamento
          </span>
        )}
        {job.data?.status === "ready" && (
          <button
            className="btn-primary"
            disabled={file.isPending}
            onClick={() =>
              file.mutate({
                path: `/financeiro/exportacoes/${id}/download`,
                name: "relatorio-financeiro.pdf",
              })
            }
          >
            <Download size={14} />
            PDF pronto · baixar
          </button>
        )}
      </div>
      <button
        className="btn-secondary"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        Meus relatórios
      </button>
      {open && (
        <section className="ui-card space-y-2 p-4">
          <h3>Relatórios disponíveis · últimos 30</h3>
          {history.isPending && <p>Consultando…</p>}
          {history.isError && <p role="alert">{errorMessage(history.error)}</p>}
          {history.data?.length === 0 && <p>Nenhum relatório vigente.</p>}
          {history.data?.map((row) => (
            <div className="flex flex-wrap items-center gap-3" key={row.id}>
              <span>
                {row.filters.start} a {row.filters.end} ·{" "}
                {row.status === "ready"
                  ? "Pronto"
                  : row.status === "queued"
                    ? "Na fila"
                    : "Falhou"}
              </span>
              <small>
                Expira em {new Date(row.expires_at).toLocaleString("pt-BR")}
              </small>
              {row.status === "ready" && (
                <button
                  className="btn-secondary"
                  onClick={() =>
                    file.mutate({
                      path: `/financeiro/exportacoes/${row.id}/download`,
                      name: "relatorio-financeiro.pdf",
                    })
                  }
                >
                  Baixar PDF
                </button>
              )}
            </div>
          ))}
        </section>
      )}
      {(create.isError || file.isError || job.isError) && (
        <p role="alert" className="feedback-error">
          {errorMessage(create.error ?? file.error ?? job.error)}
        </p>
      )}
      {job.data?.status === "failed" && (
        <p role="alert" className="feedback-error">
          {job.data.error}
        </p>
      )}
      {job.data?.status === "queued" && Date.now() - started >= 600000 && (
        <button
          className="btn-secondary"
          onClick={() => {
            setStarted(Date.now());
            void job.refetch();
          }}
        >
          Consultar processamento novamente
        </button>
      )}
    </div>
  );
}
