import { Component, type ErrorInfo, type ReactNode } from "react";
import { TriangleAlert, RotateCcw } from "lucide-react";
import { safeText } from "../lib/format";

type Props = {
  children: ReactNode;
  title?: string;
  resetKeys?: readonly unknown[];
};
type State = { error: Error | null };

/** Contains descendant render failures; async/event errors need explicit handling. */
export class ErrorBoundary extends Component<Props, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: unknown): State {
    return {
      error:
        error instanceof Error
          ? error
          : new Error("Falha inesperada ao renderizar o conteúdo."),
    };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    // Do not expose stacks or application payloads in production logs/UI.
    console.error("Falha de renderização capturada.", {
      name: error.name,
      componentStackAvailable: Boolean(info.componentStack),
    });
  }

  resetErrorBoundary = (): void => {
    this.setState({ error: null });
  };

  override componentDidUpdate(previous: Props): void {
    const before = previous.resetKeys ?? [];
    const after = this.props.resetKeys ?? [];
    if (
      this.state.error &&
      (before.length !== after.length ||
        after.some((key, i) => !Object.is(key, before[i])))
    ) {
      this.resetErrorBoundary();
    }
  }

  override render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <section
        role="alert"
        aria-label="Falha de renderização"
        className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="flex items-start gap-3">
          <span className="rounded-xl bg-amber-100 p-2 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
            <TriangleAlert size={20} aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <h2 className="font-semibold text-slate-900 dark:text-slate-100">
              {this.props.title ?? "Não foi possível renderizar este gráfico"}
            </h2>
            <p className="mt-2 break-words text-sm text-slate-600 dark:text-slate-300">
              {safeText(
                error.message,
                "Falha inesperada ao renderizar o conteúdo.",
              )}
            </p>
            <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
              Atualize os dados e tente novamente.
            </p>
            <button
              type="button"
              className="btn-secondary mt-4"
              onClick={this.resetErrorBoundary}
            >
              <RotateCcw size={14} aria-hidden="true" />
              Tentar novamente
            </button>
          </div>
        </div>
      </section>
    );
  }
}
