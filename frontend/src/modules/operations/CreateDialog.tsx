import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { request, errorMessage } from "../../shared/api/client";
import { Dialog } from "../../shared/components/Dialog";
import { useAuth } from "../identity/hooks/auth-store";
import { money, isoToday, parseMoney } from "../../shared/lib/format";
type Module = "estoque" | "vendas" | "compras" | "crm";
type Page = {
  items: { id: string; name: string; sku: string; balance: number }[];
};
export function CreateDialog({
  module,
  onClose,
  onDone,
}: {
  module: Module;
  onClose: () => void;
  onDone: () => void;
}) {
  const stock = module === "estoque";
  const user = useAuth((s) => s.session!.user);
  const [key, setKey] = useState(crypto.randomUUID());
  const [productSearch, setProductSearch] = useState("");
  const [lines, setLines] = useState([
    { product_id: "", quantity: "1", unit_price: "" },
  ]);
  const [error, setError] = useState("");
  const crm = module === "crm";
  const sale = module === "vendas" || crm;
  const [customerSearch, setCustomerSearch] = useState("");
  const [supplierName, setSupplierName] = useState("");
  const suppliers = useQuery({
    queryKey: [
      "operations",
      user.tenant_id,
      user.user_id,
      "suppliers",
      supplierName,
    ],
    queryFn: () =>
      request<{ id: string; name: string }[]>(
        `/compras/fornecedores?q=${encodeURIComponent(supplierName)}`,
      ),
    enabled: module === "compras",
  });
  const customers = useQuery({
    queryKey: ["crm", user.tenant_id, user.user_id, "selector", customerSearch],
    queryFn: () =>
      request<{ items: { id: string; name: string }[] }>(
        `/crm/clientes?source=real&page_size=100&q=${encodeURIComponent(customerSearch)}`,
      ),
    enabled: sale,
  });
  const products = useQuery({
    queryKey: [
      "operations",
      user.tenant_id,
      user.user_id,
      "select-products",
      productSearch,
    ],
    queryFn: () =>
      request<Page>(
        `/estoque/produtos?source=real&page_size=100&q=${encodeURIComponent(productSearch)}`,
      ),
    enabled: !stock,
    retry: false,
  });
  const mutation = useMutation({
    mutationFn: (body: unknown) =>
      request(
        crm
          ? "/crm/oportunidades"
          : `/${module}/${stock ? "produtos" : "pedidos"}`,
        {
          method: "POST",
          headers: { "Idempotency-Key": key },
          body: JSON.stringify(body),
        },
      ),
    onSuccess: onDone,
    onError: (e) => setError(errorMessage(e)),
  });
  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    if (stock) {
      mutation.mutate({
        sku: f.get("sku"),
        name: f.get("name"),
        category: f.get("category"),
        minimum: Number(f.get("minimum")),
      });
      return;
    }
    const items = lines.map((l) => ({
      product_id: l.product_id,
      quantity: Number(l.quantity),
      unit_price: parseMoney(l.unit_price),
    }));
    if (
      items.some(
        (l) =>
          !l.product_id ||
          !l.unit_price ||
          !Number.isInteger(l.quantity) ||
          l.quantity < 1,
      )
    ) {
      setError("Confira produto, quantidade e preço dos itens.");
      return;
    }
    if (new Set(items.map((item) => item.product_id)).size !== items.length) {
      setError("Use uma linha por produto.");
      return;
    }
    const customer = customers.data?.items.find(
      (c) => c.id === f.get("customer_id"),
    );
    if (sale && !customer) {
      setError("Selecione um cliente da lista.");
      return;
    }
    if (crm) {
      mutation.mutate({
        title: f.get("title"),
        customer_id: customer?.id,
        expected_on: f.get("due_date"),
        items,
      });
      return;
    }
    mutation.mutate({
      counterparty: sale ? customer?.name : f.get("counterparty"),
      ...(sale ? { customer_id: customer?.id } : {}),
      ordered_on: f.get("ordered_on"),
      due_date: f.get("due_date"),
      variable_cost: parseMoney(String(f.get("variable_cost") || "")) || "0.00",
      lines: items,
    });
  }
  return (
    <Dialog
      title={
        crm
          ? "Nova oportunidade"
          : stock
            ? "Novo produto"
            : module === "vendas"
              ? "Novo pedido de venda"
              : "Nova ordem de compra"
      }
      subtitle="Cadastro na operação real"
      onClose={onClose}
      busy={mutation.isPending}
    >
      <form
        onSubmit={submit}
        onChange={() => {
          setKey(crypto.randomUUID());
          setError("");
        }}
      >
        <fieldset disabled={mutation.isPending} className="space-y-4 p-6">
          {stock ? (
            <>
              <Field name="sku" label="SKU" max={40} />
              <Field name="name" label="Nome do produto" max={160} />
              <Field name="category" label="Categoria" max={40} />
              <Field
                name="minimum"
                label="Estoque mínimo (unidades inteiras)"
                type="number"
                value="0"
              />
              <p className="text-xs text-slate-500">
                O saldo inicial é zero. Registre uma entrada ou receba uma
                compra para adicionar estoque.
              </p>
            </>
          ) : (
            <>
              {sale ? (
                <>
                  <label className="field-label">
                    Buscar cliente
                    <input
                      className="form-input"
                      value={customerSearch}
                      onChange={(e) => setCustomerSearch(e.target.value)}
                    />
                  </label>
                  <label className="field-label">
                    Cliente
                    <select required name="customer_id" className="form-input">
                      <option value="">Selecionar cliente</option>
                      {customers.data?.items.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  {customers.isError && (
                    <p role="alert">{errorMessage(customers.error)}</p>
                  )}
                </>
              ) : (
                <label className="field-label">
                  Fornecedor
                  <input
                    name="counterparty"
                    className="form-input"
                    list="supplier-options"
                    required
                    minLength={2}
                    maxLength={120}
                    value={supplierName}
                    onChange={(e) => setSupplierName(e.target.value)}
                  />
                  <datalist id="supplier-options">
                    {suppliers.data?.map((s) => (
                      <option key={s.id} value={s.name} />
                    ))}
                  </datalist>
                  <small>
                    Selecione um fornecedor ou cadastre pelo nome ao salvar a
                    compra.
                  </small>
                </label>
              )}
              {crm && <Field name="title" label="Título" max={140} />}
              {!crm && (
                <label className="field-label">
                  Custos variáveis adicionais (R$; zero quando inexistentes)
                  <input
                    name="variable_cost"
                    defaultValue="0,00"
                    inputMode="decimal"
                    pattern="[0-9]+([,.][0-9]{1,2})?"
                    className="form-input"
                  />
                </label>
              )}
              <div className="grid grid-cols-2 gap-4">
                {!crm && (
                  <Field
                    name="ordered_on"
                    label="Data do pedido"
                    type="date"
                    value={isoToday()}
                  />
                )}
                <Field
                  name="due_date"
                  label={crm ? "Previsão" : "Vencimento"}
                  type="date"
                  value={isoToday()}
                />
              </div>
              <label className="field-label">
                Buscar produtos
                <input
                  className="form-input mt-2"
                  placeholder="Nome ou SKU"
                  value={productSearch}
                  onChange={(e) => setProductSearch(e.target.value)}
                />
              </label>
              {products.isError && (
                <p className="feedback-error">{errorMessage(products.error)}</p>
              )}
              {!products.isLoading && !products.data?.items.length && (
                <p className="text-xs text-amber-600">
                  Cadastre produtos reais no Estoque antes de criar pedidos.
                </p>
              )}
              {lines.map((line, index) => (
                <div
                  key={index}
                  className="space-y-2 rounded-lg border border-slate-200 p-3"
                >
                  <label className="field-label">
                    Produto {index + 1}
                    <select
                      className="form-input mt-2"
                      value={line.product_id}
                      required
                      onChange={(e) =>
                        setLines((ls) =>
                          ls.map((l, i) =>
                            i === index
                              ? { ...l, product_id: e.target.value }
                              : l,
                          ),
                        )
                      }
                    >
                      <option value="">Selecione</option>
                      {products.data?.items.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.sku} · {p.name} (saldo {p.balance})
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="grid grid-cols-2 gap-3">
                    <label className="field-label">
                      Quantidade
                      <input
                        className="form-input mt-2"
                        type="number"
                        min="1"
                        max="100000"
                        step="1"
                        required
                        value={line.quantity}
                        onChange={(e) =>
                          setLines((ls) =>
                            ls.map((l, i) =>
                              i === index
                                ? { ...l, quantity: e.target.value }
                                : l,
                            ),
                          )
                        }
                      />
                    </label>
                    <label className="field-label">
                      Preço unitário (R$)
                      <input
                        className="form-input mt-2"
                        inputMode="decimal"
                        required
                        value={line.unit_price}
                        onChange={(e) =>
                          setLines((ls) =>
                            ls.map((l, i) =>
                              i === index
                                ? { ...l, unit_price: e.target.value }
                                : l,
                            ),
                          )
                        }
                      />
                    </label>
                  </div>
                  <p className="text-sm">
                    Subtotal ·{" "}
                    {money(
                      String(
                        Number(parseMoney(line.unit_price) || 0) *
                          Number(line.quantity || 0),
                      ),
                    )}
                  </p>
                  {lines.length > 1 && (
                    <button
                      type="button"
                      className="text-xs text-rose-500"
                      onClick={() => {
                        setLines((ls) => ls.filter((_, i) => i !== index));
                        setKey(crypto.randomUUID());
                      }}
                    >
                      Remover item
                    </button>
                  )}
                </div>
              ))}
              <button
                type="button"
                className="btn-secondary"
                disabled={lines.length >= 50}
                onClick={() => {
                  setLines((ls) => [
                    ...ls,
                    { product_id: "", quantity: "1", unit_price: "" },
                  ]);
                  setKey(crypto.randomUUID());
                }}
              >
                Adicionar item
              </button>
              <p className="font-semibold">
                Total ·{" "}
                {money(
                  String(
                    lines.reduce(
                      (sum, l) =>
                        sum +
                        Math.round(
                          Number(parseMoney(l.unit_price) || 0) * 100,
                        ) *
                          Number(l.quantity || 0),
                      0,
                    ) / 100,
                  ),
                )}
              </p>
            </>
          )}
          {error && (
            <p role="alert" className="feedback-error">
              {error}
            </p>
          )}
          <button className="btn-primary w-full" disabled={mutation.isPending}>
            {mutation.isPending ? "Salvando…" : "Salvar"}
          </button>
        </fieldset>
      </form>
    </Dialog>
  );
}
export function Field({
  name,
  label,
  type = "text",
  value,
  max,
}: {
  name: string;
  label: string;
  type?: string;
  value?: string;
  max?: number;
}) {
  return (
    <label className="field-label">
      {label}
      <input
        className="form-input mt-2"
        name={name}
        type={type}
        defaultValue={value}
        required
        maxLength={max}
        min={type === "number" ? 0 : undefined}
        max={type === "number" ? 1000000 : undefined}
      />
    </label>
  );
}
