import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../../identity/hooks/auth-store";
import { request } from "../../../shared/api/client";
import { useState, type FormEvent } from "react";
import {
  ArrowDownLeft,
  ArrowUpRight,
  LoaderCircle,
  ShieldCheck,
} from "lucide-react";
import { Dialog } from "../../../shared/components/Dialog";
import { isoToday, parseMoney } from "../../../shared/lib/format";
import { errorMessage } from "../../../shared/api/client";
import { useCreateEntry } from "../api";
import {
  categories,
  type Entry,
  type EntryKind,
  type EntryStatus,
} from "../types";
export function NewEntryModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (entry: Entry) => void;
}) {
  const user = useAuth((s) => s.session!.user);
  const [center, setCenter] = useState("");
  const centers = useQuery({
    queryKey: ["cost-centers", user.tenant_id, user.user_id],
    queryFn: () =>
      request<{ id: string; name: string }[]>("/financeiro/centros-custo"),
  });
  const [kind, setKind] = useState<EntryKind>("receita");
  const [status, setStatus] = useState<EntryStatus>("pendente");
  const [description, setDescription] = useState("");
  const [counterparty, setCounterparty] = useState("");
  const [category, setCategory] = useState("Vendas");
  const [amount, setAmount] = useState("");
  const [due, setDue] = useState(isoToday());
  const [settled, setSettled] = useState(isoToday());
  const [error, setError] = useState("");
  const [key, setKey] = useState(() => crypto.randomUUID());
  const mutation = useCreateEntry();
  function changed() {
    setKey(crypto.randomUUID());
    setError("");
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (mutation.isPending) return;
    const parsed = parseMoney(amount);
    if (!parsed) {
      setError("Informe um valor maior que zero. Exemplo: 1.250,50.");
      return;
    }
    if (description.trim().length < 3) {
      setError("Descreva o lançamento com pelo menos 3 caracteres.");
      return;
    }
    mutation.mutate(
      {
        key,
        entry: {
          description: description.trim(),
          counterparty: counterparty.trim(),
          category,
          cost_center_id: center || null,
          kind,
          status,
          amount: parsed,
          due_date: due,
          settled_on: status === "concluido" ? settled : null,
        },
      },
      {
        onSuccess: (entry) => onCreated(entry),
        onError: (e) => setError(errorMessage(e)),
      },
    );
  }
  return (
    <Dialog
      title="Novo lançamento contábil"
      subtitle="Registre uma receita ou despesa no seu fluxo de caixa."
      onClose={onClose}
      busy={mutation.isPending}
    >
      <form onSubmit={submit}>
        <fieldset disabled={mutation.isPending} className="space-y-5 p-6">
          <div
            className="grid grid-cols-2 gap-3"
            role="group"
            aria-label="Tipo de lançamento"
          >
            <button
              type="button"
              aria-pressed={kind === "receita"}
              className={`type-choice ${kind === "receita" ? "type-income" : ""}`}
              onClick={() => {
                setKind("receita");
                changed();
              }}
            >
              <ArrowDownLeft size={19} />
              <span>
                Receita<small>Entrada de recursos</small>
              </span>
            </button>
            <button
              type="button"
              aria-pressed={kind === "despesa"}
              className={`type-choice ${kind === "despesa" ? "type-expense" : ""}`}
              onClick={() => {
                setKind("despesa");
                changed();
              }}
            >
              <ArrowUpRight size={19} />
              <span>
                Despesa<small>Saída de recursos</small>
              </span>
            </button>
          </div>
          <div>
            <label className="field-label" htmlFor="entry-description">
              Descrição <span>*</span>
            </label>
            <input
              autoFocus
              id="entry-description"
              className="form-input"
              placeholder="Ex.: Consultoria de desenvolvimento"
              required
              minLength={3}
              maxLength={180}
              value={description}
              onChange={(e) => {
                setDescription(e.target.value);
                changed();
              }}
            />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="field-label" htmlFor="entry-amount">
                Valor (R$) <span>*</span>
              </label>
              <input
                id="entry-amount"
                className="form-input tabular-nums"
                inputMode="decimal"
                placeholder="0,00"
                required
                maxLength={16}
                value={amount}
                onChange={(e) => {
                  setAmount(e.target.value);
                  changed();
                }}
              />
            </div>
            <div>
              <label className="field-label" htmlFor="entry-category">
                Categoria <span>*</span>
              </label>
              <select
                id="entry-category"
                className="form-input"
                value={category}
                onChange={(e) => {
                  setCategory(e.target.value);
                  changed();
                }}
              >
                {categories.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </div>
          </div>
          <label className="block text-sm">
            Centro de custo
            <select
              aria-label="Centro de custo"
              className="form-input mt-1"
              value={center}
              onChange={(e) => {
                setCenter(e.target.value);
                changed();
              }}
            >
              <option value="">Não informado</option>
              {centers.data?.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.name}
                </option>
              ))}
            </select>
          </label>
          {centers.error && (
            <p role="alert" className="text-xs text-rose-500">
              Não foi possível carregar os centros de custo.{" "}
              <button type="button" onClick={() => void centers.refetch()}>
                Tentar novamente
              </button>
            </p>
          )}
          <div>
            <label className="field-label" htmlFor="entry-counterparty">
              Cliente ou fornecedor{" "}
              <span className="!font-normal !text-slate-400">opcional</span>
            </label>
            <input
              id="entry-counterparty"
              className="form-input"
              placeholder="Nome da contraparte"
              maxLength={120}
              value={counterparty}
              onChange={(e) => {
                setCounterparty(e.target.value);
                changed();
              }}
            />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="field-label" htmlFor="entry-due">
                Vencimento <span>*</span>
              </label>
              <input
                id="entry-due"
                className="form-input"
                type="date"
                min="2000-01-01"
                max="2100-12-31"
                required
                value={due}
                onChange={(e) => {
                  setDue(e.target.value);
                  changed();
                }}
              />
            </div>
            <div>
              <label className="field-label" htmlFor="entry-status">
                Status <span>*</span>
              </label>
              <select
                id="entry-status"
                className="form-input"
                value={status}
                onChange={(e) => {
                  setStatus(e.target.value as EntryStatus);
                  changed();
                }}
              >
                <option value="pendente">Pendente</option>
                <option value="concluido">Concluído</option>
              </select>
            </div>
          </div>
          {status === "concluido" && (
            <div>
              <label className="field-label" htmlFor="entry-settled">
                Data do recebimento ou pagamento <span>*</span>
              </label>
              <input
                id="entry-settled"
                className="form-input"
                type="date"
                required
                min="2000-01-01"
                max={isoToday()}
                value={settled}
                onChange={(e) => {
                  setSettled(e.target.value);
                  changed();
                }}
              />
            </div>
          )}
          <p className="flex items-start gap-2 rounded-lg bg-slate-50 p-3 text-[11px] leading-relaxed text-slate-500">
            <ShieldCheck
              size={16}
              className="mt-0.5 shrink-0 text-indigo-500"
            />
            Este é um lançamento real, separado da demonstração. A operação será
            registrada na auditoria.
          </p>
          {error && (
            <div className="feedback-error" role="alert">
              {error}
            </div>
          )}
        </fieldset>
        <footer className="flex items-center justify-end gap-3 rounded-b-xl border-t border-slate-100 bg-slate-50/50 px-6 py-4">
          <button
            type="button"
            className="btn-secondary"
            onClick={onClose}
            disabled={mutation.isPending}
          >
            Cancelar
          </button>
          <button
            className="btn-primary"
            type="submit"
            disabled={mutation.isPending}
          >
            {mutation.isPending && (
              <LoaderCircle size={15} className="animate-spin" />
            )}
            {mutation.isPending ? "Salvando…" : "Salvar lançamento"}
          </button>
        </footer>
      </form>
    </Dialog>
  );
}
