import { currentSource, replaceFilter } from "../../shared/lib/location";
import { useState, type ComponentProps } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, ArrowRight, Pencil } from "lucide-react";
import { CreateDialog } from "../operations/CreateDialog";
import { Editor } from "../../shared/components/Editor";
import { request, errorMessage } from "../../shared/api/client";
import { useAuth } from "../identity/hooks/auth-store";
import {
  money,
  safeFormatDate,
  isoToday,
  parseMoney,
} from "../../shared/lib/format";
type Customer = {
  id: string;
  name: string;
  document: string;
  segment: string;
  email: string;
  phone: string;
  credit_limit: string;
  version: number;
};
type Opportunity = {
  id: string;
  title: string;
  stage: string;
  loss_reason?: string;
  amount: string;
  expected_on: string;
  version: number;
  order_id: string | null;
};
type Page<T> = { items: T[]; total: number };
type Form = Omit<ComponentProps<typeof Editor>, "onClose" | "onDone">;
const stages = [
  { id: "prospeccao", name: "Prospecção" },
  { id: "proposta", name: "Proposta enviada" },
  { id: "negociacao", name: "Negociação" },
  { id: "fechado", name: "Fechado" },
  { id: "perdido", name: "Perdido" },
];
export function CRMPage() {
  const user = useAuth((s) => s.session!.user),
    client = useQueryClient();
  const [source, setSource] = useState<string>(currentSource),
    [q, setQ] = useState(""),
    [page, setPage] = useState(1),
    [pipelinePage, setPipelinePage] = useState(1),
    [form, setForm] = useState<Form | null>(null),
    [notice, setNotice] = useState("");
  const [newOpportunity, setNewOpportunity] = useState(false);
  const scope = ["crm", user.tenant_id, user.user_id];
  const writable =
    source === "real" && user.permissions.includes("vendas:pedido:escrever");
  const customers = useQuery({
    queryKey: [...scope, "customers", source, q, page],
    queryFn: ({ signal }) =>
      request<Page<Customer>>(
        `/crm/clientes?source=${source}&q=${encodeURIComponent(q)}&page=${page}&page_size=50`,
        { signal },
      ),
  });
  const opportunities = useQuery({
    queryKey: [...scope, "pipeline", source, pipelinePage],
    queryFn: ({ signal }) =>
      request<Page<Opportunity>>(
        `/crm/oportunidades?source=${source}&page=${pipelinePage}`,
        { signal },
      ),
  });
  const refresh = () => {
    for (const key of ["crm", "operations", "cockpit"])
      void client.invalidateQueries({ queryKey: [key] });
  };
  const move = useMutation({
    mutationFn: ({ row, target }: { row: Opportunity; target: string }) =>
      request(
        `/crm/oportunidades/${row.id}/${target === "fechado" ? "converter" : "etapa"}`,
        {
          method: target === "fechado" ? "POST" : "PATCH",
          body: JSON.stringify({
            version: row.version,
            ...(target !== "fechado" ? { stage: target } : {}),
          }),
        },
      ),
    onSuccess: () => {
      refresh();
      setNotice(
        "Oportunidade atualizada. Pedidos convertidos estão na aba Pedidos.",
      );
    },
  });
  function customerForm(row?: Customer) {
    setForm({
      title: row ? "Editar cliente" : "Novo cliente",
      path: row
        ? `/crm/clientes/${row.id}?version=${row.version}`
        : "/crm/clientes",
      method: row ? "PUT" : "POST",
      fields: (
        [
          ["name", "Nome"],
          ["document", "CPF/CNPJ numérico"],
          ["segment", "Segmento"],
          ["email", "Email"],
          ["phone", "Telefone"],
          ["credit_limit", "Limite de crédito (R$)"],
        ] as const
      ).map(([name, label]) => ({
        name,
        label,
        type: name === "email" ? "email" : "text",
        value: row
          ? name === "credit_limit"
            ? String(row[name]).replace(".", ",")
            : row[name]
          : name === "credit_limit"
            ? "0"
            : "",
      })),
      transform: (v) => ({
        ...v,
        credit_limit:
          v.credit_limit?.trim() === "0"
            ? "0.00"
            : (parseMoney(v.credit_limit ?? "") ?? ""),
      }),
    });
  }
  return (
    <section className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="eyebrow">Relacionamento & receita</p>
          <h1 className="page-title">CRM e funil comercial</h1>
          <p className="mt-2 text-sm text-slate-500">
            Crédito verificado na conversão. Conclua o pedido para movimentar
            estoque e financeiro.
          </p>
        </div>
        <select
          aria-label="Origem CRM"
          className="form-input !w-auto"
          value={source}
          onChange={(e) => {
            replaceFilter("source", e.target.value);
            setSource(e.target.value);
            setPage(1);
            setPipelinePage(1);
          }}
        >
          <option value="demo">Demonstração</option>
          <option value="real">Operação real</option>
        </select>
      </header>
      {notice && (
        <p role="status" className="demo-strip">
          {notice}
        </p>
      )}
      {(customers.error || opportunities.error || move.error) && (
        <p role="alert" className="feedback-error">
          {errorMessage(customers.error || opportunities.error || move.error)}
        </p>
      )}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-semibold">
          Pipeline · {opportunities.data?.total ?? 0} oportunidades
        </h2>
        {writable && (
          <div className="flex flex-wrap gap-2">
            <button
              className="btn-primary"
              onClick={() => setNewOpportunity(true)}
            >
              <Plus size={16} />
              Nova oportunidade
            </button>
          </div>
        )}
      </div>
      {opportunities.isPending && (
        <p role="status">Carregando oportunidades…</p>
      )}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        {stages.map((stage, index) => (
          <div
            key={stage.id}
            className="rounded-xl border border-slate-200 bg-slate-50/60 p-4 dark:border-slate-800 dark:bg-slate-900"
          >
            <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold">
              <span className="h-2 w-2 rounded-full bg-indigo-500" />
              {stage.name}
            </h3>
            <div className="space-y-3">
              {opportunities.data?.items
                .filter((x) => x.stage === stage.id)
                .map((row) => (
                  <article
                    key={row.id}
                    className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-950"
                  >
                    <h4 className="font-medium">{row.title}</h4>
                    <p className="my-2 text-lg font-semibold">
                      {money(row.amount)}
                    </p>
                    <p className="text-xs text-slate-500">
                      Previsão: {safeFormatDate(row.expected_on)}
                    </p>
                    {writable && index < 3 && (
                      <button
                        disabled={move.isPending}
                        className="btn-secondary mt-3 !text-xs"
                        onClick={() =>
                          move.mutate({ row, target: stages[index + 1]!.id })
                        }
                      >
                        {index === 2 ? "Converter em pedido" : "Avançar"}
                        <ArrowRight size={14} />
                      </button>
                    )}
                    {writable && index < 3 && (
                      <details className="mt-2 text-xs">
                        <summary>Revisar negociação</summary>
                        {["Reagendar", "Registrar perda"].map((label, i) => (
                          <button
                            key={label}
                            className="btn-secondary mt-2"
                            onClick={() =>
                              setForm({
                                title: label,
                                method: "PATCH",
                                path: `/crm/oportunidades/${row.id}/revisar`,
                                fields: [
                                  i
                                    ? {
                                        name: "loss_reason",
                                        label: "Motivo da perda",
                                      }
                                    : {
                                        name: "expected_on",
                                        label: "Nova previsão",
                                        type: "date",
                                        value: isoToday(),
                                      },
                                ],
                                transform: (v) => ({
                                  ...v,
                                  version: row.version,
                                }),
                              })
                            }
                          >
                            {label}
                          </button>
                        ))}
                      </details>
                    )}
                    {row.loss_reason && <p>{row.loss_reason}</p>}
                    {row.order_id && (
                      <a
                        className="btn-secondary mt-3"
                        href={`/app/vendas?source=${source}&pedido=${row.order_id}`}
                      >
                        Abrir pedido · PV-{row.order_id.slice(0, 8)}
                      </a>
                    )}
                  </article>
                ))}
              {opportunities.isSuccess &&
                !opportunities.data?.items.some(
                  (x) => x.stage === stage.id,
                ) && (
                  <p className="py-6 text-center text-xs text-slate-500">
                    Nenhuma oportunidade nesta página
                  </p>
                )}
            </div>
          </div>
        ))}
      </div>
      <nav className="flex items-center gap-3">
        <button
          className="btn-secondary"
          disabled={pipelinePage === 1}
          onClick={() => setPipelinePage((x) => x - 1)}
        >
          Anterior
        </button>
        <span>Pipeline · página {pipelinePage}</span>
        <button
          className="btn-secondary"
          disabled={pipelinePage * 100 >= (opportunities.data?.total ?? 0)}
          onClick={() => setPipelinePage((x) => x + 1)}
        >
          Próxima
        </button>
      </nav>
      <div className="ui-card overflow-hidden p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-semibold">
            Clientes · {customers.data?.total ?? 0}
          </h2>
          <input
            aria-label="Buscar clientes"
            className="form-input !w-auto"
            placeholder="Buscar por nome"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(1);
            }}
          />
          {writable && (
            <button className="btn-primary" onClick={() => customerForm()}>
              <Plus size={16} />
              Novo cliente
            </button>
          )}
        </div>
        <div className="overflow-auto">
          <table className="cash-table">
            <thead>
              <tr>
                {["Cliente", "CPF/CNPJ", "Segmento", "Limite", "Ações"].map(
                  (x) => (
                    <th key={x}>{x}</th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {customers.data?.items.map((row) => (
                <tr key={row.id}>
                  <td>
                    <strong>{row.name}</strong>
                    <small className="block text-slate-500">{row.email}</small>
                  </td>
                  <td>{row.document}</td>
                  <td>{row.segment}</td>
                  <td>{money(row.credit_limit)}</td>
                  <td>
                    {writable && (
                      <button
                        aria-label={`Editar ${row.name}`}
                        className="icon-button"
                        onClick={() => customerForm(row)}
                      >
                        <Pencil size={16} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!customers.isError &&
          !customers.isPending &&
          !customers.data?.items.length && (
            <p className="p-8 text-center text-slate-500">
              Nenhum cliente encontrado
            </p>
          )}
        <nav className="mt-4 flex items-center gap-3">
          <button
            className="btn-secondary"
            disabled={page === 1}
            onClick={() => setPage((x) => x - 1)}
          >
            Anterior
          </button>
          <span>Clientes · página {page}</span>
          <button
            className="btn-secondary"
            disabled={page * 50 >= (customers.data?.total ?? 0)}
            onClick={() => setPage((x) => x + 1)}
          >
            Próxima
          </button>
        </nav>
      </div>
      {newOpportunity && (
        <CreateDialog
          module="crm"
          onClose={() => setNewOpportunity(false)}
          onDone={() => {
            setNewOpportunity(false);
            refresh();
          }}
        />
      )}
      {form && (
        <Editor
          {...form}
          onClose={() => setForm(null)}
          onDone={() => {
            setForm(null);
            refresh();
            setNotice("Cadastro salvo.");
          }}
        />
      )}
    </section>
  );
}
