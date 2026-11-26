import { currentSource, replaceFilter } from "../../shared/lib/location";
import { CreateDialog, Field } from "./CreateDialog";
import { CRMPage } from "../integration/CRMPage";
import { ErrorBoundary } from "../../shared/components/ErrorBoundary";
import { safeDateTime } from "../../shared/lib/dates";
import { Insights } from "../ecosystem/Insights";
import { rangeDays } from "../../shared/lib/format";
import { download } from "../financeiro/components/ExportButtons";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Check, History, ArrowRightLeft } from "lucide-react";
import { request, errorMessage } from "../../shared/api/client";
import { DataGrid, type Column } from "../../shared/components/DataGrid";
import { Dialog } from "../../shared/components/Dialog";
import { useAuth } from "../identity/hooks/auth-store";
import { money } from "../../shared/lib/format";
type Module = "estoque" | "vendas" | "compras";
type Row = {
  id: string;
  sku?: string;
  name?: string;
  category?: string;
  balance?: number;
  minimum?: number;
  counterparty?: string;
  total?: string;
  ordered_on?: string;
  due_date?: string;
  status?: string;
  is_simulated: boolean;
  cash_entry_id?: string | null;
};
type Page = { items: Row[]; total: number };
type Movement = {
  id: string;
  quantity: number;
  balance_after: number;
  reason: string;
  created_at: string;
};
export function OperationsPage({ module }: { module: Module }) {
  const [tab, setTab] = useState(() =>
    new URLSearchParams(location.search).get("tab") === "crm"
      ? "crm"
      : "orders",
  );
  return (
    <div className="space-y-6">
      {module === "vendas" && (
        <nav className="flex gap-2" aria-label="Visão comercial">
          <button
            className={tab === "orders" ? "btn-primary" : "btn-secondary"}
            onClick={() => {
              replaceFilter("tab", "orders");
              setTab("orders");
            }}
          >
            Pedidos
          </button>
          <button
            className={tab === "crm" ? "btn-primary" : "btn-secondary"}
            onClick={() => {
              replaceFilter("tab", "crm");
              setTab("crm");
            }}
          >
            Clientes & CRM
          </button>
        </nav>
      )}
      <ErrorBoundary key={`${module}:${tab}`}>
        {module === "vendas" && tab === "crm" ? (
          <CRMPage />
        ) : (
          <OperationsContent module={module} />
        )}
      </ErrorBoundary>
    </div>
  );
}
function OperationsContent({ module }: { module: Module }) {
  const client = useQueryClient();
  const user = useAuth((s) => s.session!.user);
  const stock = module === "estoque";
  const [source, setSource] = useState<string>(currentSource);
  const [q, setQ] = useState(
    () =>
      new URLSearchParams(location.search).get(stock ? "sku" : "pedido") || "",
  );
  const [status, setStatus] = useState("");
  const [category, setCategory] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [low, setLow] = useState(false);
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState(stock ? "name" : "ordered_on");
  const [desc, setDesc] = useState(!stock);
  const [modal, setModal] = useState(false);
  const [selected, setSelected] = useState<Row | null>(null);
  const [notice, setNotice] = useState("");
  const [confirm, setConfirm] = useState<Row | null>(null);
  const read = stock ? "estoque:saldo:ler" : `${module}:pedido:ler`;
  const canRead = user.permissions.includes(read);
  const canWrite = user.permissions.includes(
    stock ? "estoque:movimento:escrever" : `${module}:pedido:escrever`,
  );
  const params = new URLSearchParams({
    source,
    q,
    page: String(page),
    page_size: "10",
    sort,
    desc: String(desc),
  });
  if (stock) {
    params.set("category", category);
    params.set("low", String(low));
  } else {
    if (status) params.set("status", status);
    if (start) params.set("start_date", start);
    if (end) params.set("end_date", end);
  }
  const data = useQuery({
    queryKey: [
      "operations",
      user.tenant_id,
      user.user_id,
      module,
      params.toString(),
    ],
    queryFn: ({ signal }) =>
      request<Page>(`/${module}/${stock ? "produtos" : "pedidos"}?${params}`, {
        signal,
      }),
    enabled: canRead,
    retry: false,
  });
  async function invalidate() {
    await client.invalidateQueries({ queryKey: ["operations"] });
    await client.invalidateQueries({ queryKey: ["finance"] });
  }
  const exportFile = useMutation({
    mutationFn: (format: string) =>
      download(
        `/${module}/exportar?${params}&format=${format}`,
        `${module}.${format}`,
      ),
  });
  const approve = useMutation({
    mutationFn: (id: string) =>
      request(`/governanca/aprovar/purchase/${id}`, { method: "POST" }),
    onSuccess: invalidate,
  });
  const complete = useMutation({
    mutationFn: (id: string) =>
      request<Row>(`/${module}/pedidos/${id}/concluir`, { method: "POST" }),
    onSuccess: async () => {
      await invalidate();
      setConfirm(null);
      setNotice(
        module === "vendas"
          ? "Venda concluída: estoque baixado e valor a receber criado."
          : "Compra recebida: estoque atualizado e valor a pagar criado.",
      );
    },
  });
  const cancel = useMutation({
    mutationFn: (id: string) =>
      request(`/${module}/pedidos/${id}/cancelar`, { method: "POST" }),
    onSuccess: invalidate,
  });
  const orderId = stock
    ? null
    : new URLSearchParams(location.search).get("pedido");
  const detail = useQuery({
    queryKey: [
      "operations",
      user.tenant_id,
      user.user_id,
      module,
      "detail",
      orderId,
    ],
    queryFn: () =>
      request<
        Row & {
          items: {
            sku: string;
            name: string;
            quantity: number;
            unit_price: string;
          }[];
        }
      >(`/${module}/pedidos/${orderId}`),
    enabled: canRead && !!orderId,
  });
  const columns: Column<Row>[] = stock
    ? [
        {
          key: "sku",
          label: "SKU",
          sortable: true,
          render: (r) => <span className="font-mono text-xs">{r.sku}</span>,
        },
        {
          key: "name",
          label: "Produto",
          sortable: true,
          render: (r) => <strong>{r.name}</strong>,
        },
        {
          key: "category",
          label: "Categoria",
          sortable: true,
          render: (r) => r.category,
        },
        {
          key: "balance",
          label: "Saldo (un.)",
          sortable: true,
          render: (r) => (
            <span
              className={
                (r.balance ?? 0) <= (r.minimum ?? 0) ? "text-amber-600" : ""
              }
            >
              {r.balance}{" "}
              {(r.balance ?? 0) <= (r.minimum ?? 0) ? "· Repor" : ""}
            </span>
          ),
        },
        {
          key: "minimum",
          label: "Mínimo",
          sortable: true,
          render: (r) => r.minimum,
        },
        {
          key: "actions",
          label: "Movimentações",
          render: (r) => (
            <button className="btn-secondary" onClick={() => setSelected(r)}>
              <History size={14} />
              Ver / movimentar
            </button>
          ),
        },
      ]
    : [
        {
          key: "id",
          label: "Pedido",
          render: (r) => (
            <a
              className="font-mono underline"
              href={`/app/${module}?source=${source}&pedido=${r.id}`}
            >
              {module === "vendas" ? "PV" : "PC"}-{r.id.slice(0, 8)}
            </a>
          ),
        },
        {
          key: "counterparty",
          label: module === "vendas" ? "Cliente" : "Fornecedor",
          sortable: true,
          render: (r) => <strong>{r.counterparty}</strong>,
        },
        {
          key: "ordered_on",
          label: "Data",
          sortable: true,
          render: (r) => r.ordered_on,
        },
        {
          key: "total",
          label: "Total",
          sortable: true,
          render: (r) => money(r.total ?? "0"),
        },
        {
          key: "status",
          label: "Status",
          sortable: true,
          render: (r) => (
            <span
              className={`status-badge ${r.status === "completed" ? "concluido" : "pendente"}`}
            >
              {r.status === "completed"
                ? module === "vendas"
                  ? "Concluído"
                  : "Recebido"
                : r.status === "aguardando_aprovacao"
                  ? "Aguardando Aprovação"
                  : r.status === "cancelled"
                    ? "Cancelado"
                    : "Aberto"}
            </span>
          ),
        },
        {
          key: "actions",
          label: "Integração",
          render: (r) =>
            r.cash_entry_id ? (
              <span title={r.cash_entry_id} className="text-emerald-600">
                Financeiro vinculado
              </span>
            ) : r.status === "aguardando_aprovacao" &&
              !r.is_simulated &&
              user.permissions.includes("compras:aprovacao:senior") ? (
              <button
                className="btn-secondary"
                disabled={approve.isPending}
                onClick={() => approve.mutate(r.id)}
              >
                Aprovar
              </button>
            ) : canWrite && !r.is_simulated && r.status === "draft" ? (
              <>
                <button className="btn-secondary" onClick={() => setConfirm(r)}>
                  <Check size={14} />
                  {module === "vendas" ? "Concluir" : "Receber"}
                </button>
                <button
                  className="btn-secondary"
                  disabled={cancel.isPending}
                  onClick={() => {
                    if (window.confirm("Cancelar este rascunho?"))
                      cancel.mutate(r.id);
                  }}
                >
                  Cancelar rascunho
                </button>
              </>
            ) : (
              "—"
            ),
        },
      ];
  if (!canRead)
    return (
      <div className="ui-card p-8">
        Seu perfil não possui acesso a este módulo.
      </div>
    );
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap justify-between gap-4">
        <div>
          <p className="mb-2 text-xs text-indigo-500">OPERAÇÃO INTEGRADA</p>
          <h1 className="page-title">
            {stock
              ? "Estoque"
              : module === "vendas"
                ? "Vendas & CRM"
                : "Compras"}
          </h1>
          <p className="mt-2 text-sm text-slate-500">
            {stock
              ? "Produtos, reposição e rastreabilidade de movimentos."
              : module === "vendas"
                ? "Pedidos por cliente, com estoque e contas a receber conectados."
                : "Ordens por fornecedor, recebimentos e contas a pagar."}
          </p>
        </div>
        {canWrite && (
          <button
            className="btn-primary self-start"
            onClick={() => setModal(true)}
          >
            <Plus size={15} />
            {stock ? "Novo produto" : "Novo pedido"}
          </button>
        )}
      </div>
      <div className="flex flex-wrap gap-3">
        <div className="segmented">
          {["demo", "real"].map((s) => (
            <button
              className={source === s ? "selected" : ""}
              key={s}
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
        <input
          className="form-input !w-56"
          aria-label="Buscar registros"
          placeholder={
            stock ? "Buscar nome ou SKU" : "Buscar cliente ou fornecedor"
          }
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(1);
          }}
        />
        {stock ? (
          <>
            <input
              className="form-input !w-40"
              placeholder="Categoria exata"
              aria-label="Categoria"
              value={category}
              onChange={(e) => {
                setCategory(e.target.value);
                setPage(1);
              }}
            />
            <label className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={low}
                onChange={(e) => {
                  setLow(e.target.checked);
                  setPage(1);
                }}
              />
              Abaixo do mínimo
            </label>
          </>
        ) : (
          <>
            <select
              className="form-input !w-36"
              aria-label="Status"
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setPage(1);
              }}
            >
              <option value="">Todos os status</option>
              <option value="aguardando_aprovacao">Aguardando Aprovação</option>
              <option value="cancelled">Cancelado</option>
              <option value="draft">Aberto</option>
              <option value="completed">Concluído / recebido</option>
            </select>
            <input
              type="date"
              className="form-input !w-40"
              aria-label="Data inicial"
              value={start}
              onChange={(e) => {
                setStart(e.target.value);
                setPage(1);
              }}
            />
            <input
              type="date"
              className="form-input !w-40"
              aria-label="Data final"
              value={end}
              onChange={(e) => {
                setEnd(e.target.value);
                setPage(1);
              }}
            />
          </>
        )}
      </div>
      <div className="flex gap-2">
        {["csv", "xlsx"].map((format) => (
          <button
            key={format}
            className="btn-secondary"
            disabled={exportFile.isPending}
            onClick={() => exportFile.mutate(format)}
          >
            Exportar {format.toUpperCase()}
          </button>
        ))}
      </div>
      {orderId && detail.isError && (
        <p role="alert">{errorMessage(detail.error)}</p>
      )}
      {detail.data && (
        <section className="ui-card space-y-3 p-5">
          <h2 className="font-semibold">
            Itens do pedido · {detail.data.counterparty}
          </h2>
          {detail.data.items.map((line) => (
            <p key={line.sku}>
              {line.name} · {line.quantity} × {money(line.unit_price)}{" "}
              {user.permissions.includes("estoque:saldo:ler") && (
                <a
                  className="underline"
                  href={`/app/estoque?source=${source}&sku=${encodeURIComponent(line.sku)}`}
                >
                  Ver estoque
                </a>
              )}
            </p>
          ))}
          {detail.data.cash_entry_id &&
            user.permissions.includes("financeiro:lancamento:ler") && (
              <a
                className="btn-secondary"
                href={`/app/financeiro?source=${source}&lancamento=${detail.data.cash_entry_id}`}
              >
                Abrir lançamento financeiro
              </a>
            )}
        </section>
      )}
      {cancel.isError && <p role="alert">{errorMessage(cancel.error)}</p>}
      {exportFile.isError && (
        <p role="alert" className="feedback-error">
          {errorMessage(exportFile.error)}
        </p>
      )}
      {source === "demo" && (
        <p className="demo-strip">
          Dados sintéticos integrados. A demonstração é somente leitura; novos
          cadastros pertencem à operação real.
        </p>
      )}
      {notice && (
        <p role="status" className="demo-strip">
          {notice}
        </p>
      )}
      {data.isError ? (
        <p role="alert" className="feedback-error">
          {errorMessage(data.error)}
        </p>
      ) : (
        <>
          {approve.isError && (
            <p role="alert" className="feedback-error">
              {errorMessage(approve.error)}
            </p>
          )}
          {module === "vendas" && (
            <Insights
              source={source}
              start={start || rangeDays(90).start_date}
              end={end || rangeDays(90).end_date}
              salesOnly
            />
          )}
          <DataGrid
            columns={columns}
            rows={data.data?.items ?? []}
            total={data.data?.total ?? 0}
            page={page}
            size={10}
            sort={sort}
            desc={desc}
            onSort={(key) => {
              setDesc(key === sort ? !desc : false);
              setSort(key);
              setPage(1);
            }}
            onPage={setPage}
            loading={data.isFetching}
          />
        </>
      )}
      {modal && (
        <CreateDialog
          module={module}
          onClose={() => setModal(false)}
          onDone={async () => {
            await invalidate();
            setModal(false);
            setSource("real");
            setQ("");
            setStatus("");
            setCategory("");
            setStart("");
            setEnd("");
            setLow(false);
            setPage(1);
          }}
        />
      )}
      {selected && (
        <Movements
          product={selected}
          canWrite={canWrite}
          onClose={() => setSelected(null)}
          onDone={invalidate}
        />
      )}
      {confirm && (
        <Dialog
          title={module === "vendas" ? "Concluir venda" : "Receber compra"}
          subtitle={confirm.counterparty ?? "Pedido"}
          busy={complete.isPending}
          onClose={() => setConfirm(null)}
        >
          <div className="space-y-4 p-6">
            <p className="text-sm">
              Esta ação movimenta o estoque e cria um lançamento financeiro
              pendente de {money(confirm.total ?? "0")}. A operação é atômica.
            </p>
            {complete.isError && (
              <p role="alert" className="feedback-error">
                {errorMessage(complete.error)}
              </p>
            )}
            <button
              className="btn-primary"
              disabled={complete.isPending}
              onClick={() => complete.mutate(confirm.id)}
            >
              {complete.isPending ? "Processando…" : "Confirmar operação"}
            </button>
          </div>
        </Dialog>
      )}
    </div>
  );
}
function Movements({
  product,
  canWrite,
  onClose,
  onDone,
}: {
  product: Row;
  canWrite: boolean;
  onClose: () => void;
  onDone: () => Promise<void>;
}) {
  const user = useAuth((s) => s.session!.user);
  const [page, setPage] = useState(1);
  const [key, setKey] = useState(crypto.randomUUID());
  const client = useQueryClient();
  const data = useQuery({
    queryKey: [
      "operations",
      user.tenant_id,
      user.user_id,
      "movements",
      product.id,
      page,
    ],
    queryFn: () =>
      request<{ items: Movement[]; total: number }>(
        `/estoque/produtos/${product.id}/movimentos?page=${page}`,
      ),
    retry: false,
  });
  const save = useMutation({
    mutationFn: (body: unknown) =>
      request(`/estoque/produtos/${product.id}/movimentos`, {
        method: "POST",
        headers: { "Idempotency-Key": key },
        body: JSON.stringify(body),
      }),
    onSuccess: async () => {
      await onDone();
      await client.invalidateQueries({ queryKey: ["operations"] });
      setKey(crypto.randomUUID());
    },
  });
  return (
    <Dialog
      title={product.name ?? "Movimentações"}
      subtitle={product.sku ?? "Produto"}
      onClose={onClose}
      busy={save.isPending}
    >
      <div className="space-y-4 p-6">
        {canWrite && !product.is_simulated && (
          <form
            className="space-y-3"
            onChange={() => setKey(crypto.randomUUID())}
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              save.mutate({
                quantity: Number(f.get("quantity")),
                reason: f.get("reason"),
              });
            }}
          >
            <label className="field-label">
              Quantidade (+ entrada / − saída)
              <input
                className="form-input mt-2"
                name="quantity"
                type="number"
                min="-100000"
                max="100000"
                step="1"
                required
                disabled={save.isPending}
              />
            </label>
            <Field name="reason" label="Motivo da movimentação" max={180} />
            <button className="btn-primary" disabled={save.isPending}>
              <ArrowRightLeft size={14} />
              {save.isPending ? "Registrando…" : "Registrar movimento"}
            </button>
          </form>
        )}
        {(save.isError || data.isError) && (
          <p role="alert" className="feedback-error">
            {errorMessage(save.error ?? data.error)}
          </p>
        )}
        {save.isSuccess && (
          <p role="status" className="text-sm text-emerald-600">
            Movimento registrado.
          </p>
        )}
        <ul className="divide-y divide-slate-200">
          {data.data?.items.map((m) => (
            <li className="py-3 text-xs" key={m.id}>
              <strong>
                {m.quantity > 0 ? "+" : ""}
                {m.quantity} un. · saldo {m.balance_after}
              </strong>
              <p className="mt-1 text-slate-500">
                {m.reason} · {safeDateTime(m.created_at)}
              </p>
            </li>
          ))}
        </ul>
        <div className="flex justify-between">
          <button
            className="btn-secondary"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            Anterior
          </button>
          <button
            className="btn-secondary"
            disabled={page * 10 >= (data.data?.total ?? 0)}
            onClick={() => setPage((p) => p + 1)}
          >
            Próxima
          </button>
        </div>
      </div>
    </Dialog>
  );
}
