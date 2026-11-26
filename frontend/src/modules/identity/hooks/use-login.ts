import { useMutation, useQueryClient } from "@tanstack/react-query";
import { request } from "../../../shared/api/client";
import { useAuth } from "./auth-store";
import type { LoginInput, LoginResult } from "../types/auth";
export function useLogin() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: LoginInput) =>
      request<LoginResult>(
        "/identity/auth/login",
        { method: "POST", body: JSON.stringify(input) },
        false,
      ),
    onSuccess: async (result) => {
      await client.cancelQueries();
      client.clear();
      useAuth.getState().setSession({
        token: result.access_token,
        user: result.user,
        expiresAt: Date.now() + result.expires_in * 1000,
      });
      window.history.replaceState(null, "", "/app");
    },
    retry: false,
    gcTime: 0, // Login variables contain the password: discard completed mutation state.
  });
}
