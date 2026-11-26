import { currentSource, replaceFilter } from "../../shared/lib/location";
import { useState, type ComponentProps } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, BriefcaseBusiness, Landmark, Search } from "lucide-react";
import { Editor } from "../../shared/components/Editor";
import { Dialog } from "../../shared/components/Dialog";
import { request, errorMessage } from "../../shared/api/client";
import { money, parseMoney, isoToday } from "../../shared/lib/format";
import { useAuth } from "../identity/hooks/auth-store";
type Row = {
  id: string;
  name: string;
  code?: string;
  customer?: string;
  status?: string;
  budget?: string;
  hours?: string;
  cost: string;
  billed?: string;
  tag?: string;
  category?: string;
  employee_id?: string | null;
  employee_name?: string | null;
  monthly?: string;
  accumulated?: string;
  book_value?: string;
  version: number;
  is_simulated: boolean;
};
type Form = Omit<ComponentProps<typeof Editor>, "onClose" | "onDone">;
const labels: Record<string, string> = {
  planejamento: "Planejamento",
  em_execucao: "Em execução",
  concluido: "Concluído",
};
const decimal = (v: string | undefined) =>
  /^0(?:[,.]0{1,2})?$/.test(v ?? "") ? "0.00" : parseMoney(v ?? "");
export function EnterprisePage({ module }: { module: "projetos" | "ativos" }) {
  const projects = module === "projetos",
    user = useAuth((s) => s.session!.user),
    client = useQueryClient();
  const [source, setSource] = useState<string>(currentSource),
    [q, setQ] = useState(""),
    [page, setPage] = useState(1),
    [asOf, setAsOf] = useState(isoToday()),
    [form, setForm] = useState<Form | null>(null),
    [detail, setDetail] = useState<Row | null>(null),
    [notice, setNotice] = useState("");
  const permission = projects ? "projetos:projeto" : "ativos:patrimonio",
    canRead = user.permissions.includes(`${permission}:ler`),
    canWrite = user.permissions.includes(`${permission}:escrever`),
    canBill =
      user.permissions.includes("projetos:entrega:faturar") &&
      user.permissions.includes("financeiro:lancamento:escrever");
  const params = new URLSearchParams({
    source,
    q,
    page: String(page),
    ...(projects ? {} : { as_of: asOf }),
  });
  const list = useQuery({
    queryKey: [
      "enterprise",
      user.tenant_id,
      user.user_id,
      module,
      params.toString(),
    ],
    queryFn: ({ signal }) =>
      request<{ items: Row[]; total: number }>(`/${module}?${params}`, {
        signal,
      }),
    enabled: canRead,
    retry: false,
  });
  const owners = useQuery({
    queryKey: ["asset-owners", user.tenant_id, user.user_id],
    queryFn: () =>
      request<{ id: string; name: string }[]>("/ativos/responsaveis"),
    enabled: !projects && canWrite,
    retry: false,
  });
  async function invalidate() {
    await Promise.all(
      ["enterprise", "finance", "cockpit", "bi"].map((key) =>
        client.invalidateQueries({ queryKey: [key] }),
      ),
    );
  }
  const action = useMutation({
    mutationFn: ({ row, remove }: { row: Row; remove: boolean }) =>
      request(
        remove
          ? `/${module}/${row.id}?version=${row.version}`
          : `/projetos/${row.id}/status`,
        {
          method: remove ? "DELETE" : "PATCH",
          ...(remove
            ? {}
            : {
                body: JSON.stringify({
                  version: row.version,
                  status:
                    row.status === "planejamento" ? "em_execucao" : "concluido",
                }),
              }),
        },
      ),
    onSuccess: async () => {
      setNotice("Operação registrada com auditoria.");
      await invalidate();
    },
  });
  function create() {
    setForm(
      projects
        ? {
            title: "Novo projeto",
            path: "/projetos",
            fields: [
              { name: "code", label: "Código único" },
              { name: "name", label: "Nome do projeto" },
              { name: "customer", label: "Cliente ou área interna" },
              {
                name: "budget",
                label: "Orçamento de custo (R$)",
                value: "0,00",
              },
            ],
            transform: (v) => ({ ...v, budget: decimal(v.budget) }),
          }
        : {
            title: "Cadastrar patrimônio",
            path: "/ativos",
            fields: [
              { name: "tag", label: "Plaqueta única" },
              { name: "name", label: "Nome do bem" },
              { name: "category", label: "Categoria" },
              { name: "cost", label: "Custo de aquisição (R$)" },
              { name: "residual", label: "Valor residual (R$)", value: "0,00" },
              {
                name: "life_months",
                label: "Vida útil em meses",
                type: "number",
                value: "36",
              },
              {
                name: "service_on",
                label: "Entrada em serviço",
                type: "date",
                value: isoToday(),
              },
            ],
            transform: (v) => ({
              ...v,
              cost: decimal(v.cost),
              residual: decimal(v.residual),
              life_months: Number(v.life_months),
            }),
          },
    );
  }
  function hours(r: Row) {
    setForm({
      title: `Alocar horas · ${r.name}`,
      path: `/projetos/${r.id}/horas`,
      fields: [
        { name: "description", label: "Descrição do trabalho" },
        {
          name: "worked_on",
          label: "Data do trabalho",
          type: "date",
          value: isoToday(),
        },
        { name: "hours", label: "Horas (ex.: 8,50)" },
        { name: "hourly_cost", label: "Custo por hora (R$)" },
      ],
      transform: (v) => ({
        ...v,
        hours: decimal(v.hours),
        hourly_cost: decimal(v.hourly_cost),
      }),
    });
  }
  function bill(r: Row) {
    setForm({
      title: `Faturar entrega · ${r.name}`,
      path: `/projetos/${r.id}/entregas`,
      fields: [
        { name: "description", label: "Entrega / marco concluído" },
        { name: "amount", label: "Valor a receber (R$)" },
        {
          name: "due_date",
          label: "Vencimento",
          type: "date",
          value: isoToday(),
        },
      ],
      transform: (v) => ({ ...v, amount: decimal(v.amount) }),
    });
  }
  function assign(r: Row) {
    setForm({
      title: `Atribuir posse · ${r.name}`,
      path: `/ativos/${r.id}/posse`,
      method: "PUT",
      fields: [
        {
          name: "employee_id",
          label: "Responsável",
          value: r.employee_id ?? "none",
          options: [
            { value: "none", label: "Sem responsável / devolução" },
            ...(owners.data ?? []).map((u) => ({ value: u.id, label: u.name })),
          ],
        },
      ],
      transform: (v) => ({
        employee_id: v.employee_id === "none" ? null : v.employee_id,
        version: r.version,
      }),
    });
  }
  function maintain(r: Row) {
    setForm({
      title: `Registrar manutenção · ${r.name}`,
      path: `/ativos/${r.id}/manutencoes`,
      fields: [
        { name: "description", label: "Serviço realizado" },
        {
          name: "performed_on",
          label: "Data",
          type: "date",
          value: isoToday(),
        },
        { name: "cost", label: "Custo registrado (R$)", value: "0,00" },
      ],
      transform: (v) => ({ ...v, cost: decimal(v.cost) }),
    });
  }
  if (!canRead)
    return (
      <p className="ui-card p-8">Seu perfil não possui acesso a este módulo.</p>
    );
  return (
    <div className="space-y-5 page-enter">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="mb-2 text-[10px] tracking-[.2em] text-indigo-500">
            ENTERPRISE OPERATIONS
          </p>
          <h1 className="page-title flex items-center gap-3">
            {projects ? (
              <BriefcaseBusiness size={24} />
            ) : (
              <Landmark size={24} />
            )}{" "}
            {projects ? "Projetos & operações" : "Ativos & patrimônio"}
          </h1>
          <p className="mt-2 text-xs text-slate-500">
            {projects
              ? "Orçamento, esforço e entregas conectados ao Financeiro."
              : "Custódia, manutenção e depreciação gerencial dos bens."}
          </p>
        </div>
        {canWrite && (
          <button className="btn-primary" onClick={create}>
            <Plus size={15} />
            {projects ? "Novo projeto" : "Novo ativo"}
          </button>
        )}
      </header>
      <div className="flex flex-wrap gap-3">
        <select
          className="form-input !w-44"
          aria-label="Origem"
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
        <label className="search-control">
          <Search size={14} />
          <input
            aria-label="Buscar"
            placeholder="Buscar nome ou código…"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(1);
            }}
          />
        </label>
        {!projects && (
          <label className="flex items-center gap-2 text-xs text-slate-500">
            Depreciação em
            <input
              className="form-input !w-40"
              type="date"
              aria-label="Data da depreciação"
              value={asOf}
              onChange={(e) => setAsOf(e.target.value)}
            />
          </label>
        )}
      </div>
      {source === "demo" && (
        <p className="demo-strip">
          Exemplos demonstrativos em modo de leitura. Novos cadastros pertencem
          à operação real.
        </p>
      )}
      {!projects && (
        <p className="text-xs text-slate-500">
          Método linear, por meses civis completos a partir do mês seguinte à
          ativação. Não gera lançamento contábil automático. Manutenções
          registram custos sem criar pagamentos.
        </p>
      )}
      {notice && (
        <p role="status" className="demo-strip">
          {notice}
        </p>
      )}
      {(list.isError || action.isError || owners.isError) && (
        <p role="alert" className="feedback-error">
          {errorMessage(list.error ?? action.error ?? owners.error)}
        </p>
      )}
      <div className="ui-card overflow-hidden">
        <div className="overflow-auto">
          <table className="cash-table">
            <thead>
              <tr>
                {(projects
                  ? [
                      "Projeto / cliente",
                      "Orçamento",
                      "Horas / custo",
                      "Faturado",
                      "Status",
                      "Ações",
                    ]
                  : [
                      "Bem / categoria",
                      "Aquisição",
                      "Deprec. mensal",
                      "Acumulada / valor atual",
                      "Responsável",
                      "Ações",
                    ]
                ).map((c) => (
                  <th key={c}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {list.data?.items.map((r) => (
                <tr key={r.id}>
                  <td>
                    <strong>{r.name}</strong>
                    <small className="block text-slate-500">
                      {r.code ?? r.tag} · {r.customer ?? r.category}
                    </small>
                  </td>
                  {projects ? (
                    <>
                      <td>{money(r.budget ?? "0")}</td>
                      <td>
                        <strong
                          className={
                            Number(r.cost) > Number(r.budget)
                              ? "text-rose-500"
                              : ""
                          }
                        >
                          {money(r.cost)}
                        </strong>
                        <small className="block text-slate-500">
                          {r.hours} h{" "}
                          {Number(r.cost) > Number(r.budget)
                            ? "· Acima do orçamento"
                            : ""}
                        </small>
                      </td>
                      <td>{money(r.billed ?? "0")}</td>
                      <td>
                        <span
                          className={`status-badge ${r.status === "concluido" ? "concluido" : "pendente"}`}
                        >
                          {labels[r.status ?? ""]}
                        </span>
                      </td>
                    </>
                  ) : (
                    <>
                      <td>{money(r.cost)}</td>
                      <td>{money(r.monthly ?? "0")}</td>
                      <td>
                        <strong>{money(r.book_value ?? "0")}</strong>
                        <small className="block text-slate-500">
                          Depreciado: {money(r.accumulated ?? "0")}
                        </small>
                      </td>
                      <td>{r.employee_name ?? "Sem responsável"}</td>
                    </>
                  )}
                  <td>
                    <div className="flex flex-wrap gap-2">
                      <button
                        className="btn-secondary"
                        onClick={() => setDetail(r)}
                      >
                        Histórico
                      </button>
                      {!r.is_simulated && (
                        <>
                          {projects ? (
                            <>
                              {canWrite && r.status !== "concluido" && (
                                <button
                                  className="btn-secondary"
                                  disabled={action.isPending}
                                  onClick={() =>
                                    action.mutate({ row: r, remove: false })
                                  }
                                >
                                  {r.status === "planejamento"
                                    ? "Iniciar"
                                    : "Concluir"}
                                </button>
                              )}
                              {canWrite && r.status === "em_execucao" && (
                                <button
                                  className="btn-secondary"
                                  onClick={() => hours(r)}
                                >
                                  Alocar horas
                                </button>
                              )}
                              {canBill && r.status !== "planejamento" && (
                                <button
                                  className="btn-primary"
                                  onClick={() => bill(r)}
                                >
                                  Faturar entrega
                                </button>
                              )}
                            </>
                          ) : (
                            canWrite && (
                              <>
                                <button
                                  className="btn-secondary"
                                  onClick={() => assign(r)}
                                >
                                  Posse
                                </button>
                                <button
                                  className="btn-secondary"
                                  onClick={() => maintain(r)}
                                >
                                  Manutenção
                                </button>
                              </>
                            )
                          )}
                          {canWrite &&
                            (projects
                              ? r.status === "planejamento"
                              : !r.employee_id) && (
                              <button
                                className="btn-secondary"
                                disabled={action.isPending}
                                onClick={() =>
                                  action.mutate({ row: r, remove: true })
                                }
                              >
                                Arquivar
                              </button>
                            )}
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!list.data?.items.length && (
          <p className="p-10 text-center text-sm text-slate-500">
            {list.isFetching ? "Carregando…" : "Nenhum registro neste recorte."}
          </p>
        )}
        <footer className="flex justify-between p-4 text-xs">
          <span>
            {list.data?.total ?? 0} registros · página {page}
          </span>
          <div className="flex gap-2">
            <button
              className="btn-secondary"
              disabled={page <= 1 || list.isFetching}
              onClick={() => setPage((p) => p - 1)}
            >
              Anterior
            </button>
            <button
              className="btn-secondary"
              disabled={page * 10 >= (list.data?.total ?? 0) || list.isFetching}
              onClick={() => setPage((p) => p + 1)}
            >
              Próxima
            </button>
          </div>
        </footer>
      </div>
      {form && (
        <Editor
          {...form}
          onClose={() => setForm(null)}
          onDone={() => {
            setForm(null);
            setSource("real");
            setNotice("Registro salvo e auditado.");
            void invalidate();
          }}
        />
      )}
      {detail && (
        <History module={module} row={detail} onClose={() => setDetail(null)} />
      )}
    </div>
  );
}
function History({
  module,
  row,
  onClose,
}: {
  module: string;
  row: Row;
  onClose: () => void;
}) {
  const user = useAuth((s) => s.session!.user),
    [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: [
      "enterprise-history",
      user.tenant_id,
      user.user_id,
      row.id,
      page,
    ],
    queryFn: () =>
      request<{
        items?: Record<string, string>[];
        hours?: Record<string, string>[];
        deliveries?: Record<string, string>[];
      }>(
        `/${module}/${row.id}/${module === "projetos" ? "historico" : "manutencoes"}?page=${page}`,
      ),
    retry: false,
  });
  return (
    <Dialog title={`Histórico · ${row.name}`} onClose={onClose}>
      <div className="p-6 space-y-5">
        {query.isError && (
          <p role="alert" className="feedback-error">
            {errorMessage(query.error)}
          </p>
        )}
        {Object.entries(query.data ?? {}).map(([kind, rows]) => (
          <section key={kind}>
            <h3 className="card-title">
              {kind === "hours"
                ? "Horas e custos"
                : kind === "deliveries"
                  ? "Entregas faturadas"
                  : "Manutenções"}
            </h3>
            {rows.map((r) => (
              <div key={r.id} className="cockpit-row">
                <div className="flex-1">
                  <strong>{r.description}</strong>
                  <small className="block text-slate-500">
                    {r.date}
                    {r.hours ? ` · ${r.hours} h` : ""}
                    {r.cash_entry_id
                      ? ` · Financeiro: ${r.cash_entry_id.slice(0, 8)}`
                      : ""}
                  </small>
                </div>
                <strong>{money(r.amount ?? r.cost ?? "0")}</strong>
              </div>
            ))}
            {!rows.length && (
              <p className="py-4 text-xs text-slate-500">
                Sem registros nesta página.
              </p>
            )}
          </section>
        ))}
        <div className="flex gap-2">
          <button
            className="btn-secondary"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            Anterior
          </button>
          <button
            className="btn-secondary"
            disabled={
              !Object.values(query.data ?? {}).some(
                (rows) => rows.length === 20,
              )
            }
            onClick={() => setPage((p) => p + 1)}
          >
            Próxima
          </button>
        </div>
      </div>
    </Dialog>
  );
}
