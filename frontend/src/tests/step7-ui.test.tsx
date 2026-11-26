import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CRMPage } from "../modules/integration/CRMPage";
import { BankingPage } from "../modules/integration/BankingPage";
import { NotificationCenter } from "../shared/components/NotificationCenter";
import { useAuth } from "../modules/identity/hooks/auth-store";
const clients: QueryClient[] = [];
function mount(element: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  clients.push(client);
  render(<QueryClientProvider client={client}>{element}</QueryClientProvider>);
}
beforeEach(() => {
  useAuth
    .getState()
    .setSession({
      token: "test",
      expiresAt: Date.now() + 900000,
      user: {
        user_id: "u",
        tenant_id: "t",
        email: "a@example.com",
        display_name: "Admin",
        permissions: [
          "vendas:pedido:ler",
          "vendas:pedido:escrever",
          "financeiro:conciliacao:executar",
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
  for (const client of clients.splice(0)) client.clear();
  vi.unstubAllGlobals();
  useAuth.getState().clear();
});
it("creates a customer with exact decimal credit", async () => {
  const mock = vi.fn(
    async (_url: string, init?: RequestInit) =>
      new Response(
        JSON.stringify(
          init?.method === "POST" ? { id: "c" } : { items: [], total: 0 },
        ),
        { status: init?.method === "POST" ? 201 : 200 },
      ),
  );
  vi.stubGlobal("fetch", mock);
  mount(<CRMPage />);
  const ui = userEvent.setup();
  await ui.selectOptions(screen.getByLabelText("Origem CRM"), "real");
  await ui.click(screen.getByRole("button", { name: "Novo cliente" }));
  for (const [label, value] of [
    ["Nome", "Cliente teste"],
    ["CPF/CNPJ numérico", "11222333000181"],
    ["Segmento", "TI"],
    ["Email", "cliente@example.com"],
    ["Telefone", "22999999999"],
  ])
    await ui.type(screen.getByLabelText(label!), value!);
  await ui.clear(screen.getByLabelText("Limite de crédito (R$)"));
  await ui.type(screen.getByLabelText("Limite de crédito (R$)"), "1.250,50");
  await ui.click(screen.getByRole("button", { name: "Confirmar" }));
  await waitFor(() =>
    expect(mock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(
      true,
    ),
  );
  const call = mock.mock.calls.find(([, init]) => init?.method === "POST")!;
  expect(JSON.parse(call[1]!.body as string)).toMatchObject({
    credit_limit: "1250.50",
    document: "11222333000181",
  });
});
it("converts an opportunity using its version", async () => {
  const mock = vi.fn(
    async (url: string, init?: RequestInit) =>
      new Response(
        JSON.stringify(
          url.includes("oportunidades") && init?.method !== "POST"
            ? {
                items: [
                  {
                    id: "opp",
                    title: "Proposta CRM",
                    stage: "negociacao",
                    amount: "400.00",
                    expected_on: "2026-W45",
                    version: 3,
                    order_id: null,
                  },
                ],
                total: 1,
              }
            : { items: [], total: 0 },
        ),
      ),
  );
  vi.stubGlobal("fetch", mock);
  mount(<CRMPage />);
  const ui = userEvent.setup();
  await ui.selectOptions(screen.getByLabelText("Origem CRM"), "real");
  await ui.click(
    await screen.findByRole("button", { name: "Converter em pedido" }),
  );
  await waitFor(() =>
    expect(
      mock.mock.calls.some(
        ([url, init]) =>
          url.endsWith("/opp/converter") && init?.body === '{"version":3}',
      ),
    ).toBe(true),
  );
});
it("matches a reviewed movement", async () => {
  const mock = vi.fn(
    async (url: string, init?: RequestInit) =>
      new Response(
        JSON.stringify(
          url.endsWith("/candidatos")
            ? [
                {
                  id: "cash",
                  description: "Receita",
                  effective_on: null,
                  amount: "1250.50",
                },
              ]
            : init?.method === "POST"
              ? {}
              : {
                  items: [
                    {
                      id: "bank",
                      account: "LOCAL",
                      description: "Crédito real",
                      posted_on: "2026-W45",
                      amount: "1250.50",
                      cash_entry_id: null,
                    },
                  ],
                  total: 1,
                },
        ),
      ),
  );
  vi.stubGlobal("fetch", mock);
  mount(<BankingPage />);
  const ui = userEvent.setup();
  await ui.selectOptions(
    screen.getByLabelText("Origem dos movimentos"),
    "real",
  );
  await ui.click(
    await screen.findByRole("button", { name: "Revisar candidatos" }),
  );
  await ui.click(await screen.findByRole("button", { name: "Confirmar" }));
  await waitFor(() =>
    expect(
      mock.mock.calls.some(
        ([url, init]) =>
          url.endsWith("/bank/conciliar") &&
          init?.body === '{"cash_entry_id":"cash"}',
      ),
    ).toBe(true),
  );
});
it("shows real alerts and navigates to real data", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            total: 1,
            updated_at: null,
            items: [
              {
                id: "a",
                title: "Estoque crítico",
                description: "Notebook",
                path: "/app/estoque",
              },
            ],
          }),
        ),
    ),
  );
  mount(<NotificationCenter />);
  const ui = userEvent.setup();
  await ui.click(
    await screen.findByRole("button", { name: "Notificações: 1 alertas" }),
  );
  await ui.click(screen.getByRole("button", { name: /Estoque crítico/ }));
  expect(window.location.pathname + window.location.search).toBe(
    "/app/estoque?source=real",
  );
});
