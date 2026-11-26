import { beforeEach, afterEach, it, expect, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useAuth } from "../modules/identity/hooks/auth-store";
import { CockpitPage } from "../modules/ecosystem/CockpitPage";
import { EnterprisePage } from "../modules/ecosystem/EnterprisePage";
beforeEach(() => {
  useAuth
    .getState()
    .setSession({
      token: "test",
      expiresAt: Date.now() + 100000,
      user: {
        user_id: "u",
        tenant_id: "t",
        display_name: "Ana",
        email: "ana@test.com",
        permissions: [
          "identidade:dashboard:ler",
          "projetos:projeto:ler",
          "projetos:projeto:escrever",
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
it("shows the cross-sector cockpit without copying the cash ledger", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            start: "2026-11-01",
            end: "2026-11-13",
            updated_at: "2026-11-13T12:00:00Z",
            sales: {
              revenue: "3000.00",
              top_products: [
                { name: "Monitor", quantity: 3, amount: "3000.00" },
              ],
            },
            cash: null,
            stock: {
              critical: 2,
              items: [{ name: "Cabo USB", balance: 0, minimum: 5 }],
            },
            purchases: null,
            approvals: null,
            fiscal: null,
            people: null,
            audit: null,
            projects: null,
            assets: null,
          }),
        ),
    ),
  );
  mount(<CockpitPage />);
  expect(await screen.findByText("Monitor")).toBeTruthy();
  expect(screen.getByText("Cabo USB")).toBeTruthy();
  expect(screen.queryByText("Novo lançamento")).toBeNull();
  expect(screen.queryByText("Governança em tempo real")).toBeNull();
});
it("creates a project with exact cents and a retry-safe request key", async () => {
  const mock = vi.fn(
    async (_url: string, options: RequestInit) =>
      new Response(
        JSON.stringify(
          options.method === "POST" ? { id: "p" } : { items: [], total: 0 },
        ),
        { status: options.method === "POST" ? 201 : 200 },
      ),
  );
  vi.stubGlobal("fetch", mock);
  mount(<EnterprisePage module="projetos" />);
  await userEvent.click(screen.getByRole("button", { name: "Novo projeto" }));
  await userEvent.type(screen.getByLabelText("Código único"), "PRJ-1");
  await userEvent.type(
    screen.getByLabelText("Nome do projeto"),
    "Projeto Atlas",
  );
  await userEvent.type(
    screen.getByLabelText("Cliente ou área interna"),
    "Atlas",
  );
  await userEvent.clear(screen.getByLabelText("Orçamento de custo (R$)"));
  await userEvent.type(
    screen.getByLabelText("Orçamento de custo (R$)"),
    "20.000,50",
  );
  await userEvent.click(screen.getByRole("button", { name: "Confirmar" }));
  await waitFor(() =>
    expect(mock.mock.calls.some((c) => c[1].method === "POST")).toBe(true),
  );
  const call = mock.mock.calls.find((c) => c[1].method === "POST")!;
  expect(JSON.parse(call[1].body as string)).toEqual({
    code: "PRJ-1",
    name: "Projeto Atlas",
    customer: "Atlas",
    budget: "20000.50",
  });
  expect(new Headers(call[1].headers).get("Idempotency-Key")).toBeTruthy();
});
