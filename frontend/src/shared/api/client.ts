import { useAuth } from "../../modules/identity/hooks/auth-store";
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export async function request<T>(
  path: string,
  options: RequestInit = {},
  authenticated = true,
): Promise<T> {
  const response = authenticated
    ? await authenticatedFetch(`/api/v1${path}`, options)
    : await fetch(`/api/v1${path}`, {
        ...options,
        credentials: "same-origin",
        cache: "no-store",
        headers: { "Content-Type": "application/json", ...options.headers },
      });
  if (!response.ok) {
    const messages: Record<number, string> = {
      401: authenticated
        ? "Sua sessão expirou. Entre novamente."
        : "Empresa, email ou senha inválidos.",
      403: "Seu perfil não possui permissão para acessar este recurso.",
      409: "Esta solicitação já foi usada com outros dados. Revise o lançamento.",
      422: "Confira os campos informados e tente novamente.",
      429: "Muitas tentativas de acesso. Aguarde alguns minutos.",
      503: "Serviço temporariamente indisponível. Tente novamente em instantes.",
    };
    const body: unknown = await response.json().catch(() => null);
    const detail =
      body && typeof body === "object" && "detail" in body ? body.detail : null;
    throw new ApiError(
      response.status,
      (response.status === 403 ||
        response.status === 409 ||
        response.status === 422) &&
        typeof detail === "string"
        ? detail
        : (messages[response.status] ??
            "Não foi possível concluir a solicitação."),
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
export function errorMessage(error: unknown): string {
  return error instanceof ApiError
    ? error.message
    : "Não foi possível conectar. Verifique sua conexão e tente novamente.";
}

let refreshing: Promise<void> | null = null;
export function refreshSession(): Promise<void> {
  if (refreshing) return refreshing;
  const generation = useAuth.getState().generation;
  const rotate = async () => {
    if (useAuth.getState().generation !== generation) return;
    const response = await fetch("/api/v1/identity/auth/refresh", {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: { "X-ERP-Refresh": "1" },
    });
    if (useAuth.getState().generation !== generation) return;
    if (!response.ok) {
      if (response.status === 401) useAuth.getState().clear();
      throw new ApiError(
        response.status,
        response.status === 401
          ? "Sua sessão expirou. Entre novamente."
          : "Não foi possível renovar a sessão.",
      );
    }
    const result =
      (await response.json()) as import("../../modules/identity/types/auth").LoginResult;
    if (useAuth.getState().generation !== generation) return;
    useAuth
      .getState()
      .setSession({
        token: result.access_token,
        user: result.user,
        expiresAt: Date.now() + result.expires_in * 1000,
      });
  };
  refreshing = (
    typeof navigator !== "undefined" && navigator.locks
      ? navigator.locks.request("erp-session-refresh", rotate)
      : rotate()
  ).finally(() => {
    refreshing = null;
  });
  return refreshing;
}
export async function authenticatedFetch(
  url: string,
  options: RequestInit = {},
): Promise<Response> {
  const original = useAuth.getState().session;
  const send = () => {
    const headers = new Headers(options.headers);
    if (options.body && !(options.body instanceof FormData))
      headers.set("Content-Type", "application/json");
    const token = useAuth.getState().session?.token;
    if (token) headers.set("Authorization", `Bearer ${token}`);
    return fetch(url, {
      ...options,
      headers,
      credentials: "same-origin",
      cache: "no-store",
    });
  };
  const response = await send();
  if (response.status !== 401) return response;
  if (useAuth.getState().session?.token === original?.token)
    await refreshSession();
  const current = useAuth.getState().session;
  if (
    !current ||
    (original &&
      (current.user.user_id !== original.user.user_id ||
        current.user.tenant_id !== original.user.tenant_id))
  )
    throw new ApiError(
      401,
      "A sessão mudou. Repita a operação na conta atual.",
    );
  return send();
}
