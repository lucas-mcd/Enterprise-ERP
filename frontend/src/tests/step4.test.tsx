import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useTheme, initialTheme } from "../shared/state/theme";
import { ThemeToggle } from "../shared/components/ThemeToggle";
import { DataGrid } from "../shared/components/DataGrid";
import { OperationsPage } from "../modules/operations/OperationsPage";
import { useAuth } from "../modules/identity/hooks/auth-store";
beforeEach(() => {
  localStorage.clear();
  useTheme.setState({ theme: "light" });
  document.documentElement.classList.remove("dark");
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
it("detects system preference, persists choice and switches the root class", async () => {
  vi.stubGlobal("matchMedia", () => ({ matches: true }));
  expect(initialTheme()).toBe("dark");
  render(<ThemeToggle />);
  await userEvent.click(screen.getByLabelText("Ativar tema escuro"));
  expect(document.documentElement.classList.contains("dark")).toBe(true);
  expect(localStorage.getItem("erp-theme")).toBe("dark");
  await userEvent.click(screen.getByLabelText("Ativar tema claro"));
  expect(initialTheme()).toBe("light");
});
it("forwards column sorting and exposes its direction", async () => {
  const sort = vi.fn();
  render(
    <DataGrid
      columns={[
        {
          key: "name",
          label: "Produto",
          sortable: true,
          render: (r) => r.name,
        },
      ]}
      rows={[{ id: "1", name: "Monitor" }]}
      total={1}
      page={1}
      size={10}
      sort="name"
      desc={false}
      onSort={sort}
      onPage={vi.fn()}
      loading={false}
    />,
  );
  expect(screen.getByRole("columnheader").getAttribute("aria-sort")).toBe(
    "ascending",
  );
  await userEvent.click(screen.getByRole("button", { name: "Produto" }));
  expect(sort).toHaveBeenCalledWith("name");
});
it("creates a real stock product and refreshes the server grid", async () => {
  useAuth.getState().setSession({
    token: "token",
    expiresAt: Date.now() + 900000,
    user: {
      user_id: "u",
      tenant_id: "t",
      email: "a@b.com",
      display_name: "Admin",
      permissions: ["estoque:saldo:ler", "estoque:movimento:escrever"],
    },
  });
  const mock = vi
    .fn()
    .mockImplementation(
      async (_url: string, options: RequestInit) =>
        new Response(
          JSON.stringify(
            options.method === "POST" ? { id: "p" } : { items: [], total: 0 },
          ),
          { status: options.method === "POST" ? 201 : 200 },
        ),
    );
  vi.stubGlobal("fetch", mock);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <OperationsPage module="estoque" />
    </QueryClientProvider>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Novo produto" }));
  fireEvent.change(screen.getByLabelText("SKU"), {
    target: { value: "MON-01" },
  });
  fireEvent.change(screen.getByLabelText("Nome do produto"), {
    target: { value: "Monitor" },
  });
  fireEvent.change(
    screen.getByLabelText("Categoria", { selector: "input[name='category']" }),
    { target: { value: "Tecnologia" } },
  );
  await userEvent.click(screen.getByRole("button", { name: "Salvar" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  const post = mock.mock.calls.find(
    (c) => (c[1] as RequestInit).method === "POST",
  );
  expect(JSON.parse(post?.[1].body as string)).toEqual({
    sku: "MON-01",
    name: "Monitor",
    category: "Tecnologia",
    minimum: 0,
  });
  expect(
    mock.mock.calls.some((c) => String(c[0]).includes("source=real")),
  ).toBe(true);
  client.clear();
});
