import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bell, ArrowUpRight } from "lucide-react";
import { useAuth } from "../../modules/identity/hooks/auth-store";
import { request, errorMessage } from "../api/client";
import { Dialog } from "./Dialog";
import { safeFormatDate } from "../lib/format";
type Alerts = {
  total: number;
  updated_at: string;
  items: { id: string; title: string; description: string; path: string }[];
};
export function NotificationCenter() {
  const user = useAuth((s) => s.session!.user),
    [open, setOpen] = useState(false);
  const data = useQuery({
    queryKey: ["notifications", user.tenant_id, user.user_id],
    queryFn: ({ signal }) => request<Alerts>("/notificacoes", { signal }),
    refetchInterval: 30000,
    retry: false,
  });
  return (
    <>
      <button
        className="icon-button relative"
        aria-label={`Notificações: ${data.data?.total ?? 0} alertas`}
        onClick={() => setOpen(true)}
      >
        <Bell size={19} />
        {!!data.data?.total && (
          <span className="absolute -right-1 -top-1 rounded-full bg-rose-500 px-1.5 text-[10px] text-white">
            {data.data.total > 99 ? "99+" : data.data.total}
          </span>
        )}
      </button>
      {open && (
        <Dialog
          title="Central de alertas"
          subtitle="Ocorrências reais conforme suas permissões. Atualização a cada 30 segundos."
          onClose={() => setOpen(false)}
        >
          <div className="max-h-[65vh] space-y-3 overflow-y-auto p-6">
            {data.isPending && <p>Carregando alertas…</p>}
            {data.error && (
              <p role="alert">
                {errorMessage(data.error)}
                <button
                  className="btn-secondary mt-3"
                  onClick={() => void data.refetch()}
                >
                  Tentar novamente
                </button>
              </p>
            )}
            {data.data?.items.map((row) => (
              <button
                key={row.id}
                className="flex w-full items-center justify-between gap-4 rounded-xl border border-slate-200 p-4 text-left hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800"
                onClick={() => {
                  window.history.pushState(null, "", `${row.path}?source=real`);
                  window.dispatchEvent(new PopStateEvent("popstate"));
                  setOpen(false);
                }}
              >
                <div>
                  <p className="text-sm font-semibold">{row.title}</p>
                  <p className="mt-1 text-xs text-slate-500">
                    {row.description}
                  </p>
                </div>
                <ArrowUpRight size={16} />
              </button>
            ))}
            {data.data && !data.data.total && (
              <p className="p-8 text-center text-slate-500">
                Tudo em dia. Nenhum alerta operacional.
              </p>
            )}
            {data.data && (
              <p className="text-xs text-slate-500">
                Até 10 ocorrências por categoria ·{" "}
                {safeFormatDate(data.data.updated_at)}
              </p>
            )}
          </div>
        </Dialog>
      )}
    </>
  );
}
