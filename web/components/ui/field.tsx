import type { ReactNode } from "react";
import { cx } from "./cx";

/**
 * Accessibility wiring shared by every labelled control (Feature 03 §8): a visible label,
 * an optional hint, and an error linked with `aria-describedby` plus `aria-invalid`.
 * Ids are explicit (`id` prop), not `useId`, so the components stay hook-free and render
 * the same in server components and in client forms.
 */
export type FieldProps = {
  id: string;
  label: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
};

export function describedBy({ id, hint, error }: Pick<FieldProps, "id" | "hint" | "error">) {
  const ids = [hint ? `${id}-hint` : undefined, error ? `${id}-error` : undefined].filter(
    Boolean,
  );
  return ids.length > 0 ? ids.join(" ") : undefined;
}

/** Props a labelled control spreads onto its native element. */
export function controlA11y(field: Pick<FieldProps, "id" | "hint" | "error">) {
  return {
    id: field.id,
    "aria-describedby": describedBy(field),
    "aria-invalid": field.error ? true : undefined,
  } as const;
}

export function FieldHint({ id, children }: { id: string; children?: ReactNode }) {
  if (!children) return null;
  return (
    <p className="mt-1 text-sm text-ink-muted" id={`${id}-hint`}>
      {children}
    </p>
  );
}

export function FieldError({ id, children }: { id: string; children?: ReactNode }) {
  if (!children) return null;
  return (
    <p className="mt-1 text-sm font-medium text-danger" id={`${id}-error`}>
      {children}
    </p>
  );
}

export function FieldLabel({
  htmlFor,
  children,
  className,
}: {
  htmlFor: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={cx("block text-sm font-semibold text-ink", className)} htmlFor={htmlFor}>
      {children}
    </label>
  );
}

/** Border shared by text-like controls: `border-strong` meets 3:1 (SC 1.4.11). */
export const controlBorder = (invalid: boolean) =>
  invalid ? "border-danger" : "border-border-strong";
