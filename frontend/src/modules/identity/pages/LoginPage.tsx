import { ThemeToggle } from "../../../shared/components/ThemeToggle";
import { useState, type FormEvent } from "react";
import { useLogin } from "../hooks/use-login";
import { errorMessage } from "../../../shared/api/client";
const DEFAULT_TENANT = "11111111-1111-4111-8111-111111111111";
export function LoginPage() {
  const login = useLogin();
  const [tenant, setTenant] = useState(DEFAULT_TENANT);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [visible, setVisible] = useState(false);
  const [validation, setValidation] = useState("");
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (login.isPending) return;
    if (
      !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
        tenant,
      )
    ) {
      setValidation("Informe um identificador de empresa válido.");
      return;
    }
    setValidation("");
    login.mutate(
      { tenant_id: tenant, email: email.trim(), password },
      {
        onSettled: () => {
          setPassword("");
          login.reset();
        },
        onError: (error) => setValidation(errorMessage(error)),
      },
    );
  }
  return (
    <main className="login-layout">
      <div className="fixed right-5 top-5 z-50">
        <ThemeToggle />
      </div>
      <section className="login-story" aria-label="Enterprise ERP">
        <a className="brand" href="/login">
          <span className="brand-mark">E</span> enterprise
          <span className="brand-light">/erp</span>
        </a>
        <div className="story-body">
          <span className="eyebrow light">CONTROLE EM CADA DECISÃO</span>
          <h1>
            Uma operação.
            <br />
            Todas as
            <br />
            <span>possibilidades.</span>
          </h1>
          <p>
            A base para conectar pessoas, processos e informação em um só lugar.
          </p>
          <div className="story-lines">
            <span>01 / Identidade</span>
            <span>02 / Rastreabilidade</span>
            <span>03 / Gestão integrada</span>
          </div>
        </div>
        <footer className="story-footer">
          <span>ENTERPRISE PLATFORM</span>
          <span>02 — IDENTIDADE</span>
        </footer>
        <div className="orb orb-one" aria-hidden="true" />
        <div className="orb orb-two" aria-hidden="true" />
      </section>
      <section className="login-panel">
        <span className="secure-tag">
          <span /> ACESSO À PLATAFORMA
        </span>
        <div className="login-form-wrap">
          <span className="eyebrow">SEU ESPAÇO DE TRABALHO</span>
          <h2>Bem-vindo de volta.</h2>
          <p className="muted">Entre com sua conta para continuar.</p>
          <form onSubmit={submit} className="login-form">
            <label htmlFor="email">Email corporativo</label>
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="username"
              required
              maxLength={254}
              placeholder="voce@empresa.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={login.isPending}
            />
            <label htmlFor="password">Senha</label>
            <div className="password-field">
              <input
                id="password"
                name="password"
                type={visible ? "text" : "password"}
                autoComplete="current-password"
                required
                maxLength={128}
                placeholder="Sua senha de acesso"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={login.isPending}
              />
              <button
                type="button"
                onClick={() => setVisible(!visible)}
                aria-label={visible ? "Ocultar senha" : "Mostrar senha"}
              >
                {visible ? "Ocultar" : "Mostrar"}
              </button>
            </div>
            <details className="tenant-details">
              <summary>Configuração da empresa</summary>
              <label htmlFor="tenant">Identificador da empresa (tenant)</label>
              <input
                id="tenant"
                name="tenant"
                type="text"
                required
                value={tenant}
                onChange={(e) => setTenant(e.target.value.trim())}
                disabled={login.isPending}
              />
              <p>Use o identificador fornecido pelo administrador.</p>
            </details>
            {validation && (
              <div role="alert" className="error-box">
                {validation}
              </div>
            )}
            <button
              type="submit"
              className="primary-button"
              disabled={login.isPending}
            >
              {login.isPending ? "Validando acesso…" : "Entrar na plataforma"}
              <span aria-hidden="true">→</span>
            </button>
          </form>
          <p className="login-help">
            Precisa de acesso? Fale com o administrador da sua empresa.
          </p>
        </div>
        <footer className="login-footer">
          Enterprise ERP <span>Identidade e acesso</span>
        </footer>
      </section>
    </main>
  );
}
