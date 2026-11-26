import { Editor, type Field } from "../../shared/components/Editor";
import { currentSource, replaceFilter } from "../../shared/lib/location";
import { safeDateTime } from "../../shared/lib/dates";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Eye, ShieldCheck } from "lucide-react";
import { request, errorMessage } from "../../shared/api/client";
import { Dialog } from "../../shared/components/Dialog";
import { useAuth } from "../identity/hooks/auth-store";
import { money, parseMoney, isoToday } from "../../shared/lib/format";
type Module = "fiscal" | "rh" | "auditoria";
type Row = {
  id: string;
  number?: number;
  kind?: string;
  status?: string;
  regime?: string;
  base?: string;
  order_id?: string;
  taxes?: Record<string, { base: string; rate: string; amount: string }>;
  name?: string;
  registration?: string;
  department?: string;
  job_title?: string;
  base_salary?: string;
  hired_on?: string;
  is_active?: boolean;
  is_simulated?: boolean;
  month?: string;
  gross?: string;
  net?: string;
  lines?: { name: string; department: string; net: string }[];
  cash_entry_id?: string;
  actor_id?: string;
  table?: string;
  operation?: string;
  occurred_at?: string;
  diff?: Record<string, { valor_antigo: unknown; valor_novo: unknown }>;
  cancellation_reason?: string;
};
export function EcosystemPage({ module }: { module: Module }) {
  const user = useAuth((s) => s.session!.user);
  const client = useQueryClient();
  const [source, setSource] = useState<string>(currentSource);
  const [tab, setTab] = useState("colaboradores");
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [department, setDepartment] = useState("");
  const [status, setStatus] = useState("");
  const [actor, setActor] = useState("");
  const [table, setTable] = useState("");
  const [detail, setDetail] = useState<Row | null>(null);
  const [form, setForm] = useState<{
    title: string;
    path: string;
    method?: string;
    fields: Field[];
    transform?: (v: Record<string, string>) => unknown;
  } | null>(null);
  const permission =
    module === "fiscal"
      ? "fiscal:documento:ler"
      : module === "rh"
        ? "rh:folha:ler"
        : "auditoria:registro:ler";
  const allowed = user.permissions.includes(permission);
  const writable = user.permissions.includes(
    module === "fiscal" ? "fiscal:documento:emitir" : "rh:folha:processar",
  );
  const params = new URLSearchParams({
    source,
    page: String(page),
    q,
    department,
  });
  if (status)
    params.set(module === "auditoria" ? "operation" : "status", status);
  if (actor) params.set("user_id", actor);
  if (table) params.set("table", table);
  const endpoint =
    module === "fiscal"
      ? "/fiscal/notas"
      : module === "rh"
        ? `/rh/${tab}`
        : "/governanca/auditoria";
  const data = useQuery({
    queryKey: [
      "ecosystem",
      user.tenant_id,
      user.user_id,
      endpoint,
      params.toString(),
    ],
    queryFn: () =>
      request<{ items: Row[]; total: number }>(`${endpoint}?${params}`),
    enabled: allowed,
    retry: false,
    refetchInterval: module === "fiscal" ? 5000 : false,
  });
  const users = useQuery({
    queryKey: ["governance-users", user.tenant_id, user.user_id],
    queryFn: () =>
      request<{ id: string; name: string; approval_limit: string }[]>(
        "/governanca/usuarios",
      ),
    enabled: module === "auditoria",
    retry: false,
  });
  const origins = useQuery({
    queryKey: ["fiscal-origins", user.tenant_id, user.user_id],
    queryFn: () =>
      request<{ id: string; counterparty: string; kind: string }[]>(
        "/fiscal/origens",
      ),
    enabled: module === "fiscal" && writable,
    retry: false,
  });
  function employee(row?: Row) {
    setForm({
      title: row ? "Editar colaborador" : "Novo colaborador",
      path: row ? `/rh/colaboradores/${row.id}` : "/rh/colaboradores",
      method: row ? "PUT" : "POST",
      fields: [
        {
          name: "registration",
          label: "Matrícula",
          value: row?.registration ?? "",
          readonly: !!row,
        },
        { name: "name", label: "Nome", value: row?.name ?? "" },
        {
          name: "department",
          label: "Departamento",
          value: row?.department ?? "",
        },
        { name: "job_title", label: "Cargo", value: row?.job_title ?? "" },
        {
          name: "base_salary",
          label: "Salário base (R$)",
          value: row?.base_salary?.replace(".", ",") ?? "",
        },
        {
          name: "hired_on",
          label: "Admissão",
          type: "date",
          value: row?.hired_on ?? isoToday(),
        },
        {
          name: "is_active",
          label: "Situação",
          options: [
            { value: "true", label: "Ativo" },
            { value: "false", label: "Inativo" },
          ],
          value: String(row?.is_active ?? true),
        },
      ],
      transform: (v) => ({
        ...v,
        base_salary: parseMoney(v.base_salary ?? ""),
        is_active: v.is_active === "true",
      }),
    });
  }
  function create() {
    if (module === "fiscal")
      setForm({
        title: "Emitir documento simulado",
        path: "/fiscal/notas",
        fields: [
          {
            name: "order_id",
            label: "Venda concluída / compra recebida",
            options: (origins.data ?? []).map((o) => ({
              value: o.id,
              label: `${o.kind === "sale" ? "Venda" : "Compra"} ${o.id.slice(0, 8)} · ${o.counterparty}`,
            })),
          },
          {
            name: "kind",
            label: "Modelo",
            options: [
              { value: "nfe", label: "NF-e (simulada)" },
              { value: "nfse", label: "NFS-e (simulada)" },
            ],
          },
          {
            name: "regime",
            label: "Regime da simulação",
            options: [
              { value: "simples", label: "Simples Nacional" },
              { value: "presumido", label: "Lucro Presumido" },
              { value: "real", label: "Lucro Real" },
            ],
          },
        ],
      });
    else if (tab === "colaboradores") employee();
    else
      setForm({
        title: "Calcular folha base",
        path: "/rh/folhas",
        fields: [
          {
            name: "month",
            label: "Competência",
            type: "month",
            value: isoToday().slice(0, 7),
          },
        ],
      });
  }
  if (!allowed)
    return <p className="ui-card p-8">Seu perfil não possui acesso.</p>;
  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="mb-2 text-xs text-indigo-500">
            ECOSSISTEMA CORPORATIVO
          </p>
          <h1 className="page-title">
            {module === "fiscal"
              ? "Fiscal"
              : module === "rh"
                ? "Pessoas & Folha"
                : "Auditoria & Governança"}
          </h1>
        </div>
        {module !== "auditoria" && writable && (
          <button className="btn-primary" onClick={create}>
            <Plus size={15} />
            {module === "fiscal"
              ? "Emitir nota simulada"
              : tab === "folhas"
                ? "Calcular folha"
                : "Novo colaborador"}
          </button>
        )}
      </header>
      {module === "fiscal" && (
        <p className="demo-strip">
          Simulação fiscal sem validade legal. Alíquotas demonstrativas
          versionadas; não transmite documentos à SEFAZ ou prefeituras.
        </p>
      )}
      {module === "rh" && (
        <>
          <p className="demo-strip">
            Folha base gerencial: salários mensais integrais, sem descontos
            legais automáticos. A provisão segue as regras de aprovação
            financeira.
          </p>
          <div className="segmented">
            <button
              className={tab === "colaboradores" ? "selected" : ""}
              onClick={() => {
                setTab("colaboradores");
                setPage(1);
              }}
            >
              Colaboradores
            </button>
            <button
              className={tab === "folhas" ? "selected" : ""}
              onClick={() => {
                setTab("folhas");
                setPage(1);
              }}
            >
              Folha de pagamento
            </button>
          </div>
        </>
      )}
      <div className="flex flex-wrap gap-3">
        {module !== "auditoria" ? (
          <div className="segmented">
            {["demo", "real"].map((s) => (
              <button
                key={s}
                className={source === s ? "selected" : ""}
                onClick={() => {
                  replaceFilter("source", s);
                  setSource(s);
                  setPage(1);
                }}
              >
                {s === "demo" ? "Demonstração" : "Operação real"}
              </button>
            ))}
          </div>
        ) : (
          <>
            <select
              className="form-input !w-52"
              aria-label="Usuário da auditoria"
              value={actor}
              onChange={(e) => {
                setActor(e.target.value);
                setPage(1);
              }}
            >
              <option value="">Todos os usuários</option>
              {users.data?.map((u) => (
                <option value={u.id} key={u.id}>
                  {u.name}
                </option>
              ))}
            </select>
            <input
              className="form-input !w-48"
              placeholder="Tabela exata"
              aria-label="Tabela"
              value={table}
              onChange={(e) => {
                setTable(e.target.value);
                setPage(1);
              }}
            />
          </>
        )}
        {module === "rh" && tab === "colaboradores" && (
          <>
            <input
              className="form-input !w-52"
              aria-label="Buscar colaborador"
              placeholder="Buscar colaborador"
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setPage(1);
              }}
            />
            <input
              className="form-input !w-44"
              placeholder="Departamento exato"
              aria-label="Departamento"
              value={department}
              onChange={(e) => {
                setDepartment(e.target.value);
                setPage(1);
              }}
            />
          </>
        )}
        {module !== "rh" && (
          <select
            className="form-input !w-48"
            aria-label="Status ou operação"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
          >
            <option value="">Todos</option>
            {(module === "fiscal"
              ? ["autorizada", "processando", "cancelada"]
              : ["INSERT", "UPDATE", "DELETE"]
            ).map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        )}
      </div>
      {data.isError && (
        <p className="feedback-error" role="alert">
          {errorMessage(data.error)}
        </p>
      )}
      <div className="ui-card overflow-x-auto">
        <table className="cash-table">
          <thead>
            <tr>
              {(module === "fiscal"
                ? ["Número / modelo", "Regime", "Base", "Status"]
                : module === "auditoria"
                  ? ["Quando", "Usuário", "Tabela", "Operação"]
                  : tab === "folhas"
                    ? ["Competência", "Bruto", "Líquido", "Status"]
                    : ["Colaborador", "Departamento", "Cargo", "Salário base"]
              ).map((c) => (
                <th key={c}>{c}</th>
              ))}
              <th>Ações</th>
            </tr>
          </thead>
          <tbody>
            {data.data?.items.map((row) => (
              <tr key={row.id}>
                {module === "fiscal" ? (
                  <>
                    <td>
                      #{row.number} · {row.kind?.toUpperCase()}
                    </td>
                    <td>{row.regime}</td>
                    <td>{money(row.base ?? "0")}</td>
                    <td>
                      <span
                        className={`status-badge ${row.status === "autorizada" ? "concluido" : "pendente"}`}
                      >
                        {row.status}
                      </span>
                    </td>
                  </>
                ) : module === "auditoria" ? (
                  <>
                    <td>{safeDateTime(row.occurred_at)}</td>
                    <td>
                      {users.data?.find((u) => u.id === row.actor_id)?.name ??
                        row.actor_id ??
                        "Sistema"}
                    </td>
                    <td>{row.table}</td>
                    <td>{row.operation}</td>
                  </>
                ) : tab === "folhas" ? (
                  <>
                    <td>{row.month?.slice(0, 7)}</td>
                    <td>{money(row.gross ?? "0")}</td>
                    <td>{money(row.net ?? "0")}</td>
                    <td>{row.status}</td>
                  </>
                ) : (
                  <>
                    <td>
                      <strong>{row.name}</strong>
                      <small className="block text-slate-500">
                        {row.registration} ·{" "}
                        {row.is_active ? "Ativo" : "Inativo"}
                      </small>
                    </td>
                    <td>{row.department}</td>
                    <td>{row.job_title}</td>
                    <td>{money(row.base_salary ?? "0")}</td>
                  </>
                )}
                <td>
                  <div className="flex gap-2">
                    <button
                      className="btn-secondary"
                      onClick={() => setDetail(row)}
                    >
                      <Eye size={13} />
                      Detalhes
                    </button>
                    {module === "fiscal" &&
                      writable &&
                      !row.is_simulated &&
                      row.status === "autorizada" && (
                        <button
                          className="btn-secondary"
                          onClick={() =>
                            setForm({
                              title: "Cancelar simulação",
                              path: `/fiscal/notas/${row.id}/cancelar`,
                              fields: [
                                {
                                  name: "reason",
                                  label: "Justificativa (mínimo 15 caracteres)",
                                },
                              ],
                            })
                          }
                        >
                          Cancelar
                        </button>
                      )}
                    {module === "rh" &&
                      writable &&
                      !row.is_simulated &&
                      (tab === "colaboradores" ? (
                        <button
                          className="btn-secondary"
                          onClick={() => employee(row)}
                        >
                          Editar
                        </button>
                      ) : (
                        !row.cash_entry_id && (
                          <button
                            className="btn-primary"
                            onClick={() =>
                              setForm({
                                title: "Provisionar folha no Financeiro",
                                path: `/rh/folhas/${row.id}/provisionar`,
                                fields: [
                                  {
                                    name: "due_date",
                                    label: "Vencimento",
                                    type: "date",
                                    value: isoToday(),
                                  },
                                ],
                              })
                            }
                          >
                            Provisionar
                          </button>
                        )
                      ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!data.data?.items.length && (
          <p className="p-8 text-center text-sm text-slate-500">
            {data.isLoading ? "Carregando…" : "Nenhum registro encontrado."}
          </p>
        )}
        <footer className="flex items-center justify-between p-4 text-xs">
          <span>
            {data.data?.total ?? 0} registros · Página {page}
          </span>
          <div className="flex gap-2">
            <button
              className="btn-secondary"
              disabled={page === 1}
              onClick={() => setPage((p) => p - 1)}
            >
              Anterior
            </button>
            <button
              className="btn-secondary"
              disabled={
                page * (module === "auditoria" ? 20 : 10) >=
                (data.data?.total ?? 0)
              }
              onClick={() => setPage((p) => p + 1)}
            >
              Próxima
            </button>
          </div>
        </footer>
      </div>
      {module === "auditoria" && (
        <section className="ui-card p-5">
          <h2 className="card-title flex items-center gap-2">
            <ShieldCheck size={16} />
            Alçadas de aprovação
          </h2>
          <p className="mt-2 text-xs text-slate-500">
            Alterações de limite são auditadas. A alçada não substitui a
            permissão da ação.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            {users.data?.map((u) => (
              <button
                className="btn-secondary"
                key={u.id}
                onClick={() =>
                  setForm({
                    title: `Alçada · ${u.name}`,
                    path: `/governanca/usuarios/${u.id}/alcada`,
                    method: "PUT",
                    fields: [
                      {
                        name: "amount",
                        label: "Limite de aprovação (R$)",
                        value: Number(u.approval_limit)
                          .toFixed(2)
                          .replace(".", ","),
                      },
                    ],
                    transform: (v) => ({
                      amount: /^0(?:[,.]0{1,2})?$/.test(v.amount ?? "")
                        ? "0.00"
                        : parseMoney(v.amount ?? ""),
                    }),
                  })
                }
              >
                {u.name}: {money(Number(u.approval_limit).toFixed(2))}
              </button>
            ))}
          </div>
        </section>
      )}
      {detail && (
        <Dialog
          title={
            module === "auditoria"
              ? "Comparativo de alterações"
              : module === "fiscal"
                ? "Espelho fiscal simulado"
                : "Detalhes"
          }
          onClose={() => setDetail(null)}
        >
          <div className="max-h-[65vh] space-y-4 overflow-auto p-6">
            {detail.diff ? (
              <table className="w-full table-fixed text-left text-xs">
                <thead>
                  <tr>
                    <th>Campo</th>
                    <th>Valor anterior</th>
                    <th>Valor novo</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(detail.diff).map(([key, value]) => (
                    <tr className="border-t border-slate-200" key={key}>
                      <td className="break-words py-3 font-medium">{key}</td>
                      <td className="break-words whitespace-pre-wrap p-2 text-rose-500">
                        {JSON.stringify(value.valor_antigo, null, 2)}
                      </td>
                      <td className="break-words whitespace-pre-wrap p-2 text-emerald-600">
                        {JSON.stringify(value.valor_novo, null, 2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : detail.taxes ? (
              <>
                <p className="demo-strip">
                  SEM VALIDADE FISCAL · Regras DEMO-2026-01
                </p>
                <p className="text-sm">Pedido: {detail.order_id}</p>
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr>
                      <th>Tributo</th>
                      <th>Alíquota fictícia</th>
                      <th>Valor simulado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(detail.taxes).map(([name, tax]) => (
                      <tr key={name}>
                        <td className="py-3">{name}</td>
                        <td>{(Number(tax.rate) * 100).toFixed(2)}%</td>
                        <td>{money(tax.amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {detail.cancellation_reason && (
                  <p>{detail.cancellation_reason}</p>
                )}
              </>
            ) : detail.lines ? (
              <>
                <p className="text-sm">
                  Líquido base: {money(detail.net ?? "0")}
                </p>
                {detail.lines.map((line, i) => (
                  <div
                    key={i}
                    className="flex justify-between border-b border-slate-200 py-2 text-sm"
                  >
                    <span>
                      {line.name}
                      <small className="block text-slate-500">
                        {line.department}
                      </small>
                    </span>
                    <strong>{money(line.net)}</strong>
                  </div>
                ))}
              </>
            ) : (
              <p className="text-sm">
                {detail.name} · {detail.job_title} · {detail.department}
                <br />
                Admissão: {detail.hired_on}
                <br />
                Salário: {money(detail.base_salary ?? "0")}
              </p>
            )}
          </div>
        </Dialog>
      )}
      {form && (
        <Editor
          {...form}
          onClose={() => setForm(null)}
          onDone={async () => {
            setForm(null);
            await client.invalidateQueries({ queryKey: ["ecosystem"] });
            await client.invalidateQueries({ queryKey: ["governance-users"] });
            await client.invalidateQueries({ queryKey: ["finance"] });
            await client.invalidateQueries({ queryKey: ["bi"] });
            if (module !== "auditoria") setSource("real");
          }}
        />
      )}
    </div>
  );
}
