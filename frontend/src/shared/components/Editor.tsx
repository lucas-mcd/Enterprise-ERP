import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { request, errorMessage } from "../api/client";
import { Dialog } from "./Dialog";
export type Field = {
  name: string;
  label: string;
  type?: string;
  options?: { value: string; label: string }[];
  value?: string;
  readonly?: boolean;
};
export function Editor({
  title,
  path,
  method = "POST",
  fields,
  transform,
  onClose,
  onDone,
}: {
  title: string;
  path: string;
  method?: string;
  fields: Field[];
  transform?: (v: Record<string, string>) => unknown;
  onClose: () => void;
  onDone: () => void;
}) {
  const [requestKey, setRequestKey] = useState(() => crypto.randomUUID());
  const mutation = useMutation({
    mutationFn: (value: unknown) =>
      request(path, {
        method,
        headers: { "Idempotency-Key": requestKey },
        body: JSON.stringify(value),
      }),
    onSuccess: onDone,
    retry: false,
  });
  return (
    <Dialog title={title} onClose={onClose} busy={mutation.isPending}>
      <form
        onChange={() => setRequestKey(crypto.randomUUID())}
        onSubmit={(e) => {
          e.preventDefault();
          const values = Object.fromEntries(
            new FormData(e.currentTarget),
          ) as Record<string, string>;
          mutation.mutate(transform ? transform(values) : values);
        }}
      >
        <fieldset disabled={mutation.isPending} className="space-y-4 p-6">
          {fields.map((f) => (
            <label className="field-label" key={f.name}>
              {f.label}
              {f.options ? (
                <select
                  className="form-input mt-2"
                  name={f.name}
                  defaultValue={f.value ?? f.options[0]?.value}
                  required
                >
                  {f.options.map((o) => (
                    <option value={o.value} key={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  className="form-input mt-2"
                  name={f.name}
                  type={f.type ?? "text"}
                  defaultValue={f.value ?? ""}
                  readOnly={f.readonly ?? false}
                  required
                />
              )}
            </label>
          ))}
          {mutation.isError && (
            <p role="alert" className="feedback-error">
              {errorMessage(mutation.error)}
            </p>
          )}
          <button className="btn-primary w-full" disabled={mutation.isPending}>
            {mutation.isPending ? "Salvando…" : "Confirmar"}
          </button>
        </fieldset>
      </form>
    </Dialog>
  );
}
