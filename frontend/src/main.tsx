import { ErrorBoundary } from "./shared/components/ErrorBoundary";
import "./shared/state/theme";
import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useAuth } from "./modules/identity/hooks/auth-store";
import { LoginPage } from "./modules/identity/pages/LoginPage";
import { DashboardPage } from "./modules/identity/pages/DashboardPage";
import "./styles.css";
import { ApiError, refreshSession } from "./shared/api/client";
const client = new QueryClient();
function App() {
  const session = useAuth((s) => s.session);
  const [boot, setBoot] = useState<"loading" | "ready" | "error">("loading");
  const restore = () => {
    setBoot("loading");
    void refreshSession()
      .then(() => setBoot("ready"))
      .catch((error: unknown) =>
        setBoot(
          error instanceof ApiError && error.status === 401 ? "ready" : "error",
        ),
      );
  };
  useEffect(restore, []);
  useEffect(() => {
    if (boot !== "ready") return;
    if (!session) {
      void client.cancelQueries();
      client.clear();
      window.history.replaceState(null, "", "/login");
      return;
    }
    if (!window.location.pathname.startsWith("/app"))
      window.history.replaceState(null, "", "/app");
    let cancelled = false;
    let timer: number;
    const renew = () => {
      void refreshSession().catch(() => {
        if (!cancelled) timer = window.setTimeout(renew, 15000);
      });
    };
    timer = window.setTimeout(
      renew,
      Math.max(1000, session.expiresAt - Date.now() - 30000),
    );
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [session, boot]);
  if (boot !== "ready")
    return (
      <main className="grid min-h-screen place-items-center bg-slate-50 text-slate-800 dark:bg-slate-950 dark:text-slate-100">
        <div role="status" className="rounded-xl border p-8">
          {boot === "loading" ? (
            "Restaurando sua sessão…"
          ) : (
            <>
              <p>Não foi possível conectar ao serviço de sessão.</p>
              <button
                onClick={restore}
                className="mt-4 rounded-lg bg-indigo-600 px-4 py-2 text-white"
              >
                Tentar novamente
              </button>
            </>
          )}
        </div>
      </main>
    );
  return session ? <DashboardPage session={session} /> : <LoginPage />;
}
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={client}>
      <ErrorBoundary title="Não foi possível renderizar a interface">
        <App />
      </ErrorBoundary>
    </QueryClientProvider>
  </React.StrictMode>,
);
