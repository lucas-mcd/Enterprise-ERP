import {
  useMutation,
  useQuery,
  useQueryClient,
  keepPreviousData,
} from "@tanstack/react-query";
import { request } from "../../shared/api/client";
import { useAuth } from "../identity/hooks/auth-store";
import type { Entry, EntryInput, EntryPage, Filters, Summary } from "./types";
export function queryString(filters: Filters) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => {
    if (v) params.set(k, v);
  });
  return params;
}
export function useCashSummary(filters: Filters) {
  const user = useAuth((s) => s.session?.user);
  return useQuery({
    queryKey: ["finance", user?.tenant_id, user?.user_id, "summary", filters],
    queryFn: ({ signal }) =>
      request<Summary>(`/financeiro/fluxo-caixa?${queryString(filters)}`, {
        signal,
      }),
    staleTime: 15_000,
    retry: false,
  });
}
export function useEntries(filters: Filters, page: number, pageSize: number) {
  const user = useAuth((s) => s.session?.user);
  const params = queryString(filters);
  params.set("page", String(page));
  params.set("page_size", String(pageSize));
  return useQuery({
    queryKey: [
      "finance",
      user?.tenant_id,
      user?.user_id,
      "entries",
      filters,
      page,
      pageSize,
    ],
    queryFn: ({ signal }) =>
      request<EntryPage>(`/financeiro/lancamentos?${params}`, { signal }),
    placeholderData: (previous, previousQuery) =>
      previousQuery?.queryKey[1] === user?.tenant_id &&
      previousQuery?.queryKey[2] === user?.user_id &&
      JSON.stringify(previousQuery?.queryKey[4]) === JSON.stringify(filters)
        ? keepPreviousData(previous)
        : undefined,
    staleTime: 15_000,
    retry: false,
  });
}
export function useCreateEntry() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ entry, key }: { entry: EntryInput; key: string }) =>
      request<Entry>("/financeiro/lancamentos", {
        method: "POST",
        headers: { "Idempotency-Key": key },
        body: JSON.stringify(entry),
      }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["finance"] });
      await client.invalidateQueries({ queryKey: ["dashboard"] });
    },
    retry: false,
  });
}
