import { useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";
export function Dialog({
  title,
  subtitle,
  onClose,
  busy = false,
  children,
}: {
  title: string;
  subtitle?: string;
  onClose: () => void;
  busy?: boolean;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = ref.current;
    const focusBefore = document.activeElement;
    element?.showModal();
    return () => {
      element?.close();
      if (focusBefore instanceof HTMLElement && document.contains(focusBefore))
        focusBefore.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="erp-dialog"
      aria-labelledby="dialog-title"
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onClose();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget && !busy) onClose();
      }}
    >
      <div className="dialog-surface">
        <header className="flex items-start justify-between gap-4 border-b border-slate-100 px-6 py-5">
          <div>
            <h2
              id="dialog-title"
              className="text-lg font-semibold tracking-tight text-slate-950"
            >
              {title}
            </h2>
            {subtitle && (
              <p className="mt-1 text-xs leading-relaxed text-slate-500">
                {subtitle}
              </p>
            )}
          </div>
          <button
            type="button"
            className="icon-button"
            aria-label="Fechar modal"
            onClick={onClose}
            disabled={busy}
          >
            <X size={18} />
          </button>
        </header>
        {children}
      </div>
    </dialog>
  );
}
