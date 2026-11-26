import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { parseMoney, money } from "../shared/lib/format";
import { NewEntryModal } from "../modules/financeiro/components/NewEntryModal";
import { EntryTable } from "../modules/financeiro/components/EntryTable";
import { useAuth } from "../modules/identity/hooks/auth-store";

beforeEach(() => {
  useAuth.getState().setSession({
    token: "test",
    expiresAt: Date.now() + 900000,
    user: {
      user_id: "u",
      tenant_id: "t",
      email: "a@b.com",
      display_name: "Admin",
      permissions: ["financeiro:lancamento:escrever"],
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
it("converts Brazilian values exactly and rejects ambiguous or invalid amounts", () => {
  expect(parseMoney("1.250,50")).toBe("1250.50");
  expect(parseMoney("0,01")).toBe("0.01");
  expect(parseMoney("999.999.999,99")).toBe("999999999.99");
  for (const value of ["0", "-1", "1,001", "1.25", "1e3", "1000000000", "NaN"])
    expect(parseMoney(value)).toBeNull();
  expect(money("999999999.99")).toBe("R$ 999.999.999,99");
});
it("retries with the same idempotency key and sends exact cents without client tenant", async () => {
  let posts = 0;
  const fetchMock = vi.fn(async (url: string, options?: RequestInit) => {
    if (url.includes("centros-custo")) return new Response("[]");
    if (options?.method === "POST" && posts++ === 0) throw new TypeError("Network error");
    return new Response(JSON.stringify({ id: "entry" }), { status: 201 });
  });
  vi.stubGlobal("fetch", fetchMock);
  const created = vi.fn();
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <NewEntryModal onClose={vi.fn()} onCreated={created} />
    </QueryClientProvider>,
  );
  const ui = userEvent.setup();
  await ui.type(screen.getByLabelText(/Descrição/), "Consultoria");
  await ui.type(screen.getByLabelText(/Valor/), "1.250,50");
  await ui.click(screen.getByRole("button", { name: "Salvar lançamento" }));
  await screen.findByRole("alert");
  await ui.click(screen.getByRole("button", { name: "Salvar lançamento" }));
  await waitFor(() => expect(created).toHaveBeenCalledOnce());
  const calls = fetchMock.mock.calls.filter(([, options]) => options?.method === "POST");
  const first = calls[0]?.[1] as RequestInit;
  const second = calls[1]?.[1] as RequestInit;
  expect(new Headers(first.headers).get("Idempotency-Key")).toBe(
    new Headers(second.headers).get("Idempotency-Key"),
  );
  expect(JSON.parse(first.body as string)).toMatchObject({
    amount: "1250.50",
    status: "pendente",
    settled_on: null,
  });
  expect(JSON.parse(first.body as string)).not.toHaveProperty("tenant_id");
  client.clear();
});
it("paginates and forwards status filters without local-only filtering", async () => {
  const page = vi.fn(),
    filter = vi.fn();
  render(
    <QueryClientProvider client={new QueryClient()}>
      <EntryTable
        data={{ items: [], total: 36, page: 1, page_size: 10 }}
        filters={{
          source: "demo",
          start_date: "2026-01-01",
          end_date: "2026-03-31",
          q: "",
          kind: "",
          status: "",
          category: "",
        }}
        onFilter={filter}
        search=""
        onSearch={vi.fn()}
        page={1}
        onPage={page}
        size={10}
        onSize={vi.fn()}
        loading={false}
      />
    </QueryClientProvider>,
  );
  const ui = userEvent.setup();
  expect(
    (
      screen.getByRole("button", {
        name: "Página anterior",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
  await ui.click(screen.getByRole("button", { name: "Próxima página" }));
  expect(page).toHaveBeenCalledWith(2);
  await ui.selectOptions(
    screen.getByLabelText("Filtrar por status"),
    "concluido",
  );
  expect(filter).toHaveBeenCalledWith("status", "concluido");
});
