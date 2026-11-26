import { currentSource, replaceFilter } from "../../shared/lib/location";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Upload, ArrowRightLeft, CheckCircle2 } from "lucide-react";
import { useAuth } from "../identity/hooks/auth-store";
import { request, errorMessage } from "../../shared/api/client";
import { Dialog } from "../../shared/components/Dialog";
import { safeFormatDate, money, isoToday } from "../../shared/lib/format";
type Movement = {
  id: string;
  account: string;
  description: string;
  posted_on: string;
  amount: string;
  cash_entry_id: string | null;
};
type Candidate = {
  id: string;
  description: string;
  effective_on: string;
  amount: string;
};
export function BankingPage() {
  const user = useAuth((s) => s.session!.user),
    client = useQueryClient();
  const [source, setSource] = useState<string>(currentSource),
    [page, setPage] = useState(1),
    [selected, setSelected] = useState<Movement | null>(null),
    [notice, setNotice] = useState(""),
    [fileError, setFileError] = useState(""),
    [reference, setReference] = useState(() => crypto.randomUUID());
  const scope = ["banking", user.tenant_id, user.user_id];
  const data = useQuery({
    queryKey: [...scope, source, page],
    queryFn: ({ signal }) =>
      request<{ items: Movement[]; total: number }>(
        `/financeiro/conciliacao/movimentos?source=${source}&page=${page}`,
        { signal },
      ),
  });
  const refresh = () => {
    for (const key of ["banking", "finance", "bi", "cockpit", "notifications"])
      void client.invalidateQueries({ queryKey: [key] });
  };
  const importFile = useMutation({
    mutationFn: (body: unknown) =>
      request("/financeiro/conciliacao/importar", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      refresh();
      setNotice("Extrato importado. Revise os candidatos antes de conciliar.");
    },
  });
  const simulate = useMutation({
    mutationFn: () =>
      request("/financeiro/conciliacao/simular", {
        method: "POST",
        body: JSON.stringify({ reference }),
      }),
    onSuccess: () => {
      refresh();
      setReference(crypto.randomUUID());
      setNotice(
        "Lote local criado a partir de até 20 lançamentos reais. Nenhum banco externo foi acessado.",
      );
    },
  });
  const candidates = useQuery({
    queryKey: [...scope, "candidates", selected?.id],
    enabled: !!selected,
    queryFn: () =>
      request<Candidate[]>(
        `/financeiro/conciliacao/movimentos/${selected!.id}/candidatos`,
      ),
  });
  const match = useMutation({
    mutationFn: (cash: string) =>
      request(`/financeiro/conciliacao/movimentos/${selected!.id}/conciliar`, {
        method: "POST",
        body: JSON.stringify({ cash_entry_id: cash }),
      }),
    onSuccess: () => {
      setSelected(null);
      refresh();
      setNotice("Conciliação concluída e baixa financeira registrada.");
    },
  });
  const [preview, setPreview] = useState<{
    account: string;
    reference: string;
    entries: { description: string; amount: string; posted_on: string }[];
  } | null>(null);
  function sample() {
    const day = isoToday();
    const example = {
      account: "Conta treinamento",
      reference: `VENDA-${day}`,
      entries: [
        {
          external_id: `CREDITO-${day}`,
          posted_on: day,
          description: "Recebimento Aurora",
          amount: "600.00",
        },
      ],
    };
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(example, null, 2)], {
        type: "application/json",
      }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = "extrato-treinamento.json";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  async function upload(file?: File) {
    if (!file) return;
    setFileError("");
    try {
      if (file.size > 1024 * 1024)
        throw new Error("Use um JSON de até 1 MB e 500 movimentos.");
      const body: unknown = JSON.parse(await file.text());
      if (
        !body ||
        typeof body !== "object" ||
        !("entries" in body) ||
        !Array.isArray(body.entries) ||
        !body.entries.length ||
        body.entries.length > 500 ||
        !("account" in body) ||
        typeof body.account !== "string" ||
        !("reference" in body) ||
        typeof body.reference !== "string" ||
        body.entries.some(
          (row) =>
            !row ||
            typeof row.description !== "string" ||
            typeof row.amount !== "string" ||
            typeof row.posted_on !== "string",
        )
      )
        throw new Error(
          "Confira conta, referência e movimentos no arquivo de exemplo.",
        );
      setPreview({
        account: body.account,
        reference: body.reference,
        entries: body.entries,
      });
    } catch (e) {
      setFileError(e instanceof Error ? e.message : "Arquivo inválido.");
    }
  }
  const error = data.error || importFile.error || simulate.error;
  return (
    <section className="space-y-6">
      <header className="flex flex-wrap justify-between gap-4">
        <div>
          <p className="eyebrow">Tesouraria</p>
          <h1 className="page-title">Conciliação bancária</h1>
          <p className="mt-2 text-sm text-slate-500">
            Mesmo valor e direção · tolerância de 3 dias · confirmação manual
          </p>
        </div>
        <select
          aria-label="Origem dos movimentos"
          className="form-input !w-auto"
          value={source}
          onChange={(e) => {
            replaceFilter("source", e.target.value);
            setSource(e.target.value);
            setPage(1);
          }}
        >
          <option value="demo">Demonstração</option>
          <option value="real">Operação real</option>
        </select>
      </header>
      {source === "real" && (
        <div className="flex flex-wrap items-center gap-3">
          <label className="btn-secondary">
            <Upload size={16} />
            Importar extrato JSON
            <input
              aria-label="Arquivo de extrato JSON"
              type="file"
              accept="application/json,.json"
              className="sr-only"
              disabled={importFile.isPending}
              onChange={(e) => {
                void upload(e.target.files?.[0]);
                e.target.value = "";
              }}
            />
          </label>
          <button
            className="btn-primary"
            disabled={simulate.isPending}
            onClick={() => simulate.mutate()}
          >
            <ArrowRightLeft size={16} />
            {simulate.isPending ? "Gerando…" : "Simular lote local"}
          </button>
          <button className="btn-secondary" onClick={sample}>
            Baixar extrato de exemplo
          </button>
        </div>
      )}
      {preview && (
        <Dialog
          title="Prévia do extrato"
          onClose={() => setPreview(null)}
          busy={importFile.isPending}
        >
          <div className="space-y-3 p-5">
            <p>
              {preview.account} · {preview.reference} · {preview.entries.length}{" "}
              movimentos
            </p>
            {preview.entries.slice(0, 10).map((row, i) => (
              <p key={i}>
                {safeFormatDate(row.posted_on)} · {row.description} ·{" "}
                {money(row.amount)}
              </p>
            ))}
            {importFile.isError && (
              <p role="alert">{errorMessage(importFile.error)}</p>
            )}
            <button
              className="btn-primary"
              disabled={importFile.isPending}
              onClick={() =>
                importFile.mutate(preview, {
                  onSuccess: () => setPreview(null),
                })
              }
            >
              Confirmar importação
            </button>
          </div>
        </Dialog>
      )}
      {notice && (
        <p role="status" className="demo-strip">
          {notice}
        </p>
      )}
      {(error || fileError) && (
        <p role="alert" className="feedback-error">
          {fileError || errorMessage(error)}
        </p>
      )}
      <div className="ui-card overflow-auto">
        <table className="cash-table">
          <thead>
            <tr>
              {["Data", "Conta / descrição", "Valor", "Status", "Ação"].map(
                (x) => (
                  <th key={x}>{x}</th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {data.data?.items.map((row) => (
              <tr key={row.id}>
                <td>{safeFormatDate(row.posted_on)}</td>
                <td>
                  {row.description}
                  <small className="block text-slate-500">{row.account}</small>
                </td>
                <td
                  className={
                    Number(row.amount) < 0
                      ? "text-rose-500"
                      : "text-emerald-600"
                  }
                >
                  {money(row.amount)}
                </td>
                <td>
                  <span
                    className={`rounded-full px-2 py-1 text-xs ${row.cash_entry_id ? "bg-emerald-500/10 text-emerald-600" : "bg-amber-500/10 text-amber-600"}`}
                  >
                    {row.cash_entry_id ? "Conciliado" : "A revisar"}
                  </span>
                </td>
                <td>
                  {!row.cash_entry_id && (
                    <button
                      className="btn-secondary"
                      onClick={() => {
                        match.reset();
                        setSelected(row);
                      }}
                    >
                      Revisar candidatos
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data.isPending ? (
          <p className="p-8 text-center">Carregando movimentos…</p>
        ) : (
          data.isSuccess &&
          !data.data.items.length && (
            <p className="p-8 text-center text-slate-500">
              Sem movimentos no período
            </p>
          )
        )}
      </div>
      <nav className="flex items-center gap-4">
        <button
          className="btn-secondary"
          disabled={page === 1}
          onClick={() => setPage((x) => x - 1)}
        >
          Anterior
        </button>
        <span>
          Página {page} · {data.data?.total ?? 0} movimentos
        </span>
        <button
          className="btn-secondary"
          disabled={page * 20 >= (data.data?.total ?? 0)}
          onClick={() => setPage((x) => x + 1)}
        >
          Próxima
        </button>
      </nav>
      {selected && (
        <Dialog
          title="Revisar conciliação"
          subtitle={`${selected.description} · ${money(selected.amount)}`}
          onClose={() => setSelected(null)}
          busy={match.isPending}
        >
          <div className="space-y-3 p-6">
            <p className="text-sm text-slate-500">
              Confirme a contraparte e a data. Pendentes serão baixados na data
              do extrato.
            </p>
            {candidates.isPending && <p>Buscando candidatos…</p>}
            {(candidates.error || match.error) && (
              <p role="alert" className="feedback-error">
                {errorMessage(candidates.error || match.error)}
              </p>
            )}
            {candidates.data?.map((row) => (
              <div
                key={row.id}
                className="flex items-center justify-between gap-3 rounded-xl border p-4 dark:border-slate-800"
              >
                <div>
                  <p>{row.description}</p>
                  <small>
                    {safeFormatDate(row.effective_on)} · {money(row.amount)}
                  </small>
                </div>
                <button
                  className="btn-primary"
                  disabled={source === "demo" || match.isPending}
                  onClick={() => match.mutate(row.id)}
                >
                  <CheckCircle2 size={16} />
                  Confirmar
                </button>
              </div>
            ))}
            {candidates.isSuccess && !candidates.data.length && (
              <p className="py-6 text-center text-slate-500">
                Nenhum lançamento compatível disponível.
              </p>
            )}
            {source === "demo" && (
              <p className="text-xs text-slate-500">
                Demonstração somente para leitura.
              </p>
            )}
          </div>
        </Dialog>
      )}
    </section>
  );
}
