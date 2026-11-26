import { NotificationCenter } from "../../../shared/components/NotificationCenter";
import { ErrorBoundary } from "../../../shared/components/ErrorBoundary";

import { BriefcaseBusiness, Landmark } from "lucide-react";

import { ThemeToggle } from "../../../shared/components/ThemeToggle";
import { BrowserRouter, useLocation, useNavigate } from "react-router-dom";
import { currentSource } from "../../../shared/lib/location";
import { Suspense, lazy, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUpRight,
  Boxes,
  Building2,
  ChevronRight,
  CircleHelp,
  Command,
  FileCheck2,
  LayoutDashboard,
  LockKeyhole,
  LogOut,
  Menu,
  Package,
  ShieldCheck,
  ShoppingCart,
  Users,
  Wallet,
  X,
} from "lucide-react";
import { useAuth } from "../hooks/auth-store";
import { request, errorMessage } from "../../../shared/api/client";

import type { Dashboard, Session } from "../types/auth";
import { Dialog } from "../../../shared/components/Dialog";
const CockpitPage = lazy(() =>
  import("../../ecosystem/CockpitPage").then((m) => ({
    default: m.CockpitPage,
  })),
);
const FinancePage = lazy(() =>
  import("../../financeiro/FinancePage").then((m) => ({
    default: m.FinancePage,
  })),
);
const EnterprisePage = lazy(() =>
  import("../../ecosystem/EnterprisePage").then((m) => ({
    default: m.EnterprisePage,
  })),
);
const EcosystemPage = lazy(() =>
  import("../../ecosystem/EcosystemPage").then((m) => ({
    default: m.EcosystemPage,
  })),
);
const OperationsPage = lazy(() =>
  import("../../operations/OperationsPage").then((m) => ({
    default: m.OperationsPage,
  })),
);
export function DashboardPage({ session }: { session: Session }) {
  return (
    <BrowserRouter>
      <Workspace session={session} />
    </BrowserRouter>
  );
}
function Workspace({ session }: { session: Session }) {
  const client = useQueryClient();
  const { user } = session;
  const route = useLocation();
  const path = route.pathname;
  const go = useNavigate();
  const [help, setHelp] = useState(false);
  const mobile = useRef<HTMLDialogElement>(null);
  const canFinance = user.permissions.includes("financeiro:lancamento:ler");
  const profile = useQuery({
    queryKey: ["dashboard", user.tenant_id, user.user_id],
    queryFn: ({ signal }) =>
      request<Dashboard>("/identity/dashboard", { signal }),
    staleTime: 30_000,
    retry: false,
  });
  const logout = useMutation({
    mutationFn: () =>
      request<void>("/identity/auth/logout", { method: "POST" }),
    onSuccess: async () => {
      await client.cancelQueries();
      client.clear();
      useAuth.getState().clear();
    },
    retry: false,
  });
  const enterprise =
    path === "/app/projetos"
      ? "projetos"
      : path === "/app/ativos"
        ? "ativos"
        : null;
  const ledger = path === "/app/financeiro";
  const ecosystem =
    path === "/app/fiscal"
      ? "fiscal"
      : path === "/app/rh"
        ? "rh"
        : path === "/app/auditoria"
          ? "auditoria"
          : null;
  const operation =
    path === "/app/estoque"
      ? "estoque"
      : path === "/app/vendas"
        ? "vendas"
        : path === "/app/compras"
          ? "compras"
          : null;
  function navigate(value: string) {
    void go(value + "?source=" + currentSource());
    mobile.current?.close();
  }
  function nav() {
    return (
      <>
        <a
          href="/app"
          className="shell-brand"
          onClick={(e) => {
            e.preventDefault();
            navigate("/app");
          }}
        >
          <span>
            <Command size={19} />
          </span>
          enterprise<span className="brand-version">ERP</span>
        </a>
        <div className="tenant-switch">
          <span className="tenant-avatar">
            <Building2 size={16} />
          </span>
          <div className="min-w-0">
            <strong className="block truncate">
              {profile.data?.tenant_name ?? "Seu workspace"}
            </strong>
            <small>Ambiente corporativo</small>
          </div>
        </div>
        <span className="nav-label">WORKSPACE</span>
        <nav aria-label="Navegação principal">
          <a
            className={`nav-link ${!ledger && !operation && !ecosystem && !enterprise ? "active" : ""}`}
            href="/app"
            aria-current={
              !ledger && !operation && !ecosystem && !enterprise
                ? "page"
                : undefined
            }
            onClick={(e) => {
              e.preventDefault();
              navigate("/app");
            }}
          >
            <LayoutDashboard size={17} />
            Visão geral
          </a>
          {canFinance ? (
            <a
              className={`nav-link ${ledger ? "active" : ""}`}
              href="/app/financeiro"
              aria-current={ledger ? "page" : undefined}
              onClick={(e) => {
                e.preventDefault();
                navigate("/app/financeiro");
              }}
            >
              <Wallet size={17} />
              Financeiro
              <span className="nav-indicator" />
            </a>
          ) : (
            <button
              className="nav-link"
              disabled
              title="Seu perfil não possui acesso ao Financeiro"
            >
              <Wallet size={17} />
              Financeiro
              <LockKeyhole size={12} className="ml-auto" />
            </button>
          )}
          <span className="nav-label mt-7">MÓDULOS</span>
          {[
            {
              name: "Vendas & CRM",
              icon: ShoppingCart,
              path: "vendas",
              permission: "vendas:pedido:ler",
            },
            {
              name: "Compras",
              icon: Package,
              path: "compras",
              permission: "compras:pedido:ler",
            },
            {
              name: "Estoque",
              icon: Boxes,
              path: "estoque",
              permission: "estoque:saldo:ler",
            },
          ].map((item) => (
            <button
              key={item.path}
              className={`nav-link ${operation === item.path ? "active" : ""}`}
              disabled={!user.permissions.includes(item.permission)}
              title={
                !user.permissions.includes(item.permission)
                  ? "Seu perfil não possui acesso"
                  : item.name
              }
              onClick={() => navigate(`/app/${item.path}`)}
            >
              <item.icon size={17} />
              {item.name}
            </button>
          ))}
          {[
            {
              name: "Projetos & operações",
              icon: BriefcaseBusiness,
              path: "projetos",
              permission: "projetos:projeto:ler",
            },
            {
              name: "Ativos & patrimônio",
              icon: Landmark,
              path: "ativos",
              permission: "ativos:patrimonio:ler",
            },
          ].map((item) => (
            <button
              key={item.path}
              disabled={!user.permissions.includes(item.permission)}
              className={`nav-link ${enterprise === item.path ? "active" : ""}`}
              onClick={() => navigate(`/app/${item.path}`)}
            >
              <item.icon size={17} />
              {item.name}
            </button>
          ))}
          {[
            {
              name: "Fiscal",
              icon: FileCheck2,
              path: "fiscal",
              permission: "fiscal:documento:ler",
            },
            {
              name: "Pessoas",
              icon: Users,
              path: "rh",
              permission: "rh:folha:ler",
            },
            {
              name: "Auditoria & Governança",
              icon: ShieldCheck,
              path: "auditoria",
              permission: "identidade:usuario:gerenciar",
            },
          ].map((item) => (
            <button
              key={item.path}
              disabled={!user.permissions.includes(item.permission)}
              className={`nav-link ${ecosystem === item.path ? "active" : ""}`}
              onClick={() => navigate(`/app/${item.path}`)}
            >
              <item.icon size={17} />
              {item.name}
            </button>
          ))}
        </nav>
        <div className="mt-auto pt-10">
          <div className="sidebar-note">
            <span className="flex items-center gap-2 font-medium text-slate-600">
              <ShieldCheck size={14} />
              Acesso protegido
            </span>
            <p>Suas ações respeitam as permissões do seu perfil.</p>
          </div>
          <button className="nav-link mt-3" onClick={() => setHelp(true)}>
            <CircleHelp size={16} />
            Sobre este workspace
            <ArrowUpRight size={13} className="ml-auto" />
          </button>
          <div className="profile-row">
            <span className="profile-avatar">
              {user.display_name.slice(0, 1)}
            </span>
            <div className="min-w-0">
              <strong className="truncate">{user.display_name}</strong>
              <small className="truncate">{user.email}</small>
            </div>
            <button
              className="icon-button ml-auto"
              title="Sair da conta"
              aria-label="Sair da conta"
              disabled={logout.isPending}
              onClick={() => logout.mutate()}
            >
              <LogOut size={15} />
            </button>
          </div>
        </div>
      </>
    );
  }
  return (
    <div className="erp-shell">
      <aside className="desktop-sidebar">{nav()}</aside>
      <dialog
        ref={mobile}
        className="mobile-nav"
        onClick={(e) => {
          if (e.target === e.currentTarget) mobile.current?.close();
        }}
      >
        <div className="relative flex min-h-full flex-col p-5">
          <button
            className="icon-button absolute right-3 top-3"
            aria-label="Fechar menu"
            onClick={() => mobile.current?.close()}
          >
            <X size={18} />
          </button>
          {nav()}
        </div>
      </dialog>
      <div className="shell-body">
        <header className="shell-topbar">
          <div className="flex items-center gap-3">
            <button
              className="icon-button lg:hidden"
              aria-label="Abrir menu"
              onClick={() => mobile.current?.showModal()}
            >
              <Menu size={18} />
            </button>
            <span className="hidden text-slate-400 sm:inline">Workspace</span>
            <ChevronRight
              size={12}
              className="hidden text-slate-300 sm:block"
            />
            <span className="font-medium text-slate-700">
              {enterprise
                ? enterprise === "projetos"
                  ? "Projetos"
                  : "Patrimônio"
                : ecosystem
                  ? {
                      fiscal: "Fiscal",
                      rh: "Pessoas",
                      auditoria: "Governança",
                    }[ecosystem]
                  : operation
                    ? {
                        estoque: "Estoque",
                        vendas: "Vendas & CRM",
                        compras: "Compras",
                      }[operation]
                    : ledger
                      ? "Financeiro"
                      : "Visão geral"}
            </span>
          </div>
          <div className="flex items-center gap-4">
            <ErrorBoundary title="Alertas indisponíveis">
              <NotificationCenter />
            </ErrorBoundary>
            <ThemeToggle />
            <span className="connection-badge">
              <span />
              Sessão ativa
            </span>
            <span className="h-5 w-px bg-slate-200" />
            <button
              className="icon-button"
              aria-label="Ajuda do workspace"
              onClick={() => setHelp(true)}
            >
              <CircleHelp size={17} />
            </button>
            <span className="profile-avatar !h-7 !w-7 !text-[10px]">
              {user.display_name.slice(0, 1)}
            </span>
          </div>
        </header>
        <main className="shell-content" id="main-content">
          {logout.isError && (
            <div className="feedback-error mb-4" role="alert">
              {errorMessage(logout.error)}
            </div>
          )}
          <ErrorBoundary
            key={route.key}
            title="Não foi possível renderizar este painel"
            resetKeys={[path, user.tenant_id, user.user_id]}
          >
            <Suspense fallback={<p role="status">Carregando módulo…</p>}>
              {enterprise ? (
                <EnterprisePage key={enterprise} module={enterprise} />
              ) : ecosystem ? (
                <EcosystemPage key={ecosystem} module={ecosystem} />
              ) : operation ? (
                <OperationsPage key={operation} module={operation} />
              ) : ledger ? (
                canFinance ? (
                  <FinancePage />
                ) : (
                  <div className="ui-card p-8">
                    Seu perfil não possui acesso ao Financeiro.
                  </div>
                )
              ) : (
                <CockpitPage />
              )}
            </Suspense>
          </ErrorBoundary>
          <footer className="shell-footer">
            <span>
              Enterprise ERP <span className="mx-2 text-slate-300">/</span>{" "}
              Gestão conectada
            </span>
            <span>Versão 0.8.0</span>
          </footer>
        </main>
      </div>
      {help && (
        <Dialog
          title="Seu workspace"
          subtitle="Identidade, segurança e gestão de caixa."
          onClose={() => setHelp(false)}
        >
          <div className="space-y-4 p-6 text-sm leading-relaxed text-slate-600">
            <p>
              O Financeiro permite consultar e registrar receitas e despesas. Na
              opção Demonstração, os gráficos usam uma série sintética; suas
              movimentações ficam na opção Movimentações reais.
            </p>
            <p>
              “Realizado” considera apenas registros concluídos. O resultado do
              período não inclui um saldo bancário inicial.
            </p>
            <p>
              A sessão é renovada automaticamente. O logout revoga o acesso
              neste dispositivo.
            </p>
            <button className="btn-primary" onClick={() => setHelp(false)}>
              Entendi
            </button>
          </div>
        </Dialog>
      )}
    </div>
  );
}
