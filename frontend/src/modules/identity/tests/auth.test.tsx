import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LoginPage } from "../pages/LoginPage";
import { useAuth } from "../hooks/auth-store";
import { request } from "../../../shared/api/client";
const user = {
  user_id: "user-1",
  tenant_id: "tenant-1",
  email: "admin@enterprise.com",
  display_name: "Admin",
  permissions: ["identidade:perfil:ler"],
};
function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <LoginPage />
    </QueryClientProvider>,
  );
  return client;
}
beforeEach(() => {
  useAuth.getState().clear();
  localStorage.clear();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
describe("authentication", () => {
  it("submits credentials, stores session in memory and redirects", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          access_token: "token",
          expires_in: 900,
          token_type: "bearer",
          user,
        }),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    setup();
    const ui = userEvent.setup();
    await ui.type(
      screen.getByLabelText("Email corporativo"),
      "admin@enterprise.com",
    );
    await ui.type(screen.getByLabelText("Senha"), "Some-Password-2026!");
    await ui.click(
      screen.getByRole("button", { name: /Entrar na plataforma/ }),
    );
    await waitFor(() =>
      expect(useAuth.getState().session?.token).toBe("token"),
    );
    expect(window.location.pathname).toBe("/app");
    expect(localStorage.length).toBe(0);
    expect(
      JSON.parse(fetchMock.mock.calls[0]?.[1].body as string).tenant_id,
    ).toBe("11111111-1111-4111-8111-111111111111");
  });
  it("shows invalid credentials without creating a session and clears password", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("{}", { status: 401 })),
    );
    setup();
    const ui = userEvent.setup();
    await ui.type(
      screen.getByLabelText("Email corporativo"),
      "admin@enterprise.com",
    );
    await ui.type(screen.getByLabelText("Senha"), "wrong");
    await ui.click(
      screen.getByRole("button", { name: /Entrar na plataforma/ }),
    );
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain("inválidos"),
    );
    expect(useAuth.getState().session).toBeNull();
    expect((screen.getByLabelText("Senha") as HTMLInputElement).value).toBe("");
  });
  it("clears the current session on a protected 401", async () => {
    useAuth
      .getState()
      .setSession({ token: "old", user, expiresAt: Date.now() + 900000 });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("{}", { status: 401 })),
    );
    await expect(request("/identity/me")).rejects.toThrow("expirou");
    expect(useAuth.getState().session).toBeNull();
  });
  it("an obsolete 401 does not erase a newer session", async () => {
    useAuth
      .getState()
      .setSession({ token: "old", user, expiresAt: Date.now() + 900000 });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async () => {
        useAuth
          .getState()
          .setSession({ token: "new", user, expiresAt: Date.now() + 900000 });
        return new Response("{}", { status: 401 });
      }),
    );
    await expect(request("/identity/me")).rejects.toThrow();
    expect(useAuth.getState().session?.token).toBe("new");
  });
});
