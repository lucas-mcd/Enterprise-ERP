import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useAuth } from "../modules/identity/hooks/auth-store";
import CashCharts from "../modules/financeiro/components/CashCharts";
import { EntryTable } from "../modules/financeiro/components/EntryTable";
import { EcosystemPage } from "../modules/ecosystem/EcosystemPage";
import type { Entry } from "../modules/financeiro/types";
// Chart rendering dimensions are tested by the browser; this exercises controls.
vi.mock("recharts", async () => {
  const actual = await vi.importActual<object>("recharts");
  return { ...actual, ResponsiveContainer: () => null };
});
beforeEach(() => {
  useAuth.getState().setSession({
    token: "test",
    expiresAt: Date.now() + 900000,
    user: {
      user_id: "u",
      tenant_id: "t",
      email: "a@b.com",
      display_name: "Admin",
      permissions: [
        "financeiro:lancamento:escrever",
        "rh:folha:ler",
        "rh:folha:processar",
        "auditoria:registro:ler",
      ],
    },
  });
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function () {
    this.removeAttribute("open");
  };
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  useAuth.getState().clear();
});
function mount(node: React.ReactNode) {
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      {node}
    </QueryClientProvider>,
  );
}
it("toggles all cash series independently", async () => {
  render(
    <CashCharts
      summary={{
        source: "demo",
        total_records: 1,
        income: "10.00",
        expense: "2.00",
        net: "8.00",
        pending_income: "0.00",
        pending_expense: "0.00",
        points: [
          {
            day: "2026-11-01",
            income: "10.00",
            expense: "2.00",
            pending_income: "0.00",
            pending_expense: "0.00",
          },
        ],
        expense_categories: [],
      }}
    />,
  );
  for (const label of ["Receitas", "Despesas", "Saldo Líquido", "Previsto"]) {
    const input = screen.getByLabelText(label) as HTMLInputElement;
    const before = input.checked;
    await userEvent.click(input);
    expect(input.checked).toBe(!before);
  }
});
it("submits selected versions and reports insufficient approval limit", async () => {
  const mock = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({ detail: "Alçada insuficiente para este valor." }),
        { status: 403 },
      ),
    )
    .mockResolvedValueOnce(new Response(JSON.stringify({ updated: 1 })));
  vi.stubGlobal("fetch", mock);
  const entry: Entry = {
    id: "cash-1",
    description: "Compra de servidor",
    counterparty: "Fornecedor",
    category: "Infraestrutura",
    kind: "despesa",
    status: "aguardando_aprovacao",
    amount: "6000.00",
    currency: "BRL",
    due_date: "2026-11-12",
    settled_on: null,
    effective_on: "2026-11-12",
    is_simulated: false,
    version: 3,
  };
  mount(
    <EntryTable
      data={{ items: [entry], total: 1, page: 1, page_size: 10 }}
      filters={{
        source: "real",
        start_date: "2026-11-01",
        end_date: "2026-11-30",
        q: "",
        status: "",
        kind: "",
        category: "",
      }}
      onFilter={vi.fn()}
      search=""
      onSearch={vi.fn()}
      page={1}
      onPage={vi.fn()}
      size={10}
      onSize={vi.fn()}
      loading={false}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Aprovar" }));
  expect((await screen.findByRole("alert")).textContent).toContain(
    "Alçada insuficiente",
  );
  await userEvent.click(screen.getByLabelText("Selecionar Compra de servidor"));
  await userEvent.click(
    screen.getByRole("button", { name: "Baixar pagos / recebidos" }),
  );
  await waitFor(() => expect(mock).toHaveBeenCalledTimes(2));
  expect(mock.mock.calls[1]?.[0]).toBe("/api/v1/financeiro/lotes/baixar");
  expect(
    JSON.parse((mock.mock.calls[1]?.[1] as RequestInit).body as string).rows,
  ).toEqual([{ id: "cash-1", version: 3 }]);
});
it("shows an audit before/after comparison", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async (url: string) =>
        new Response(
          JSON.stringify(
            url.includes("usuarios")
              ? []
              : {
                  items: [
                    {
                      id: "log",
                      table: "employees",
                      operation: "UPDATE",
                      occurred_at: "2026-11-12T12:00:00Z",
                      diff: {
                        base_salary: {
                          valor_antigo: "4000.00",
                          valor_novo: "5000.00",
                        },
                      },
                    },
                  ],
                  total: 1,
                },
          ),
        ),
    ),
  );
  mount(<EcosystemPage module="auditoria" />);
  await userEvent.click(
    await screen.findByRole("button", { name: "Detalhes" }),
  );
  expect(screen.getByText("Valor anterior")).toBeTruthy();
  expect(screen.getByText('"4000.00"')).toBeTruthy();
  expect(screen.getByText('"5000.00"')).toBeTruthy();
});
