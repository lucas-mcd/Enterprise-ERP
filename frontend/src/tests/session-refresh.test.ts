import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  request,
  refreshSession,
  authenticatedFetch,
} from "../shared/api/client";
import { useAuth } from "../modules/identity/hooks/auth-store";
const user = {
  user_id: "u",
  tenant_id: "t",
  email: "a@example.com",
  display_name: "Admin",
  permissions: [],
};
const renewed = () =>
  new Response(JSON.stringify({ access_token: "new", expires_in: 900, user }));
beforeEach(() =>
  useAuth.getState().setSession({ token: "old", expiresAt: Date.now(), user }),
);
afterEach(() => {
  vi.unstubAllGlobals();
  useAuth.getState().clear();
});
it("coalesces concurrent 401s preserving the mutation body and idempotency key", async () => {
  const mock = vi.fn(async (url: string, options?: RequestInit) =>
    url.endsWith("/refresh")
      ? renewed()
      : new Response(JSON.stringify({ ok: true }), {
          status:
            new Headers(options?.headers).get("Authorization") === "Bearer new"
              ? 200
              : 401,
        }),
  );
  vi.stubGlobal("fetch", mock);
  const options = {
    method: "POST",
    headers: { "Idempotency-Key": "same-key" },
    body: '{"amount":"10.00"}',
  };
  await Promise.all([request("/one", options), request("/two", options)]);
  expect(
    mock.mock.calls.filter(([url]) => url.endsWith("/refresh")),
  ).toHaveLength(1);
  const calls = mock.mock.calls.filter(([url]) => !url.endsWith("/refresh"));
  expect(calls).toHaveLength(4);
  for (const [, value] of calls) {
    expect(value?.body).toBe(options.body);
    expect(new Headers(value?.headers).get("Idempotency-Key")).toBe("same-key");
  }
});
it("retains session during a refresh outage", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response("{}", { status: 503 })),
  );
  await expect(refreshSession()).rejects.toMatchObject({ status: 503 });
  expect(useAuth.getState().session?.token).toBe("old");
});
it("restores a session through a cookie request", async () => {
  useAuth.getState().clear();
  const mock = vi.fn(async () => renewed());
  vi.stubGlobal("fetch", mock);
  await refreshSession();
  expect(mock).toHaveBeenCalledWith(
    "/api/v1/identity/auth/refresh",
    expect.objectContaining({
      credentials: "same-origin",
      headers: { "X-ERP-Refresh": "1" },
    }),
  );
  expect(useAuth.getState().session?.token).toBe("new");
});
it("renews a protected download", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, options?: RequestInit) =>
      url.endsWith("refresh")
        ? renewed()
        : new Response("csv", {
            status:
              new Headers(options?.headers).get("Authorization") ===
              "Bearer new"
                ? 200
                : 401,
          }),
    ),
  );
  expect(await (await authenticatedFetch("/api/v1/file")).text()).toBe("csv");
});
it("never replays a mutation in a different account", async () => {
  const mock = vi.fn(async () => {
    useAuth
      .getState()
      .setSession({
        token: "other",
        expiresAt: Date.now() + 900000,
        user: { ...user, tenant_id: "other" },
      });
    return new Response("{}", { status: 401 });
  });
  vi.stubGlobal("fetch", mock);
  await expect(
    request("/mutate", { method: "POST", body: "{}" }),
  ).rejects.toThrow("sessão mudou");
  expect(mock).toHaveBeenCalledTimes(1);
});
