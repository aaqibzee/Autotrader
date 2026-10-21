import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cx } from "./cx";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
/**
 * `sm` 36px and `md` 40px clear WCAG 2.2's 24×24 minimum. `touch` is 44px, for primary
 * mobile actions (save, contact, call, filter; Feature 03 §8).
 */
export type ButtonSize = "sm" | "md" | "touch";

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-brand text-surface hover-state:bg-brand-strong",
  secondary: "border border-border-strong bg-surface text-ink hover-state:bg-sunken",
  ghost: "bg-transparent text-brand-strong hover-state:bg-brand-tint",
  danger: "bg-danger text-surface hover-state:bg-ink",
};

const SIZES: Record<ButtonSize, string> = {
  sm: "min-h-9 px-3 text-sm",
  md: "min-h-10 px-4 text-sm",
  touch: "min-h-11 min-w-11 px-5 text-base",
};

export const buttonClasses = (variant: ButtonVariant, size: ButtonSize, className?: string) =>
  cx(
    "inline-flex items-center justify-center gap-2 rounded-md font-semibold transition-colors",
    "disabled:cursor-not-allowed disabled:opacity-50",
    VARIANTS[variant],
    SIZES[size],
    className,
  );

/**
 * Indeterminate spinner. It is only ever shown while a request is in flight, and every
 * request has a time limit (10 s in the browser, lib/api/client.ts), so it cannot spin
 * forever (Feature 03 §3). Still under reduced motion.
 */
export function Spinner({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden="true"
      className={cx("size-4 shrink-0 animate-spin motion-reduce:animate-none", className)}
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-90" d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="4" />
    </svg>
  );
}

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Disables the button and shows a spinner; the label stays so the width does not jump. */
  loading?: boolean;
  /** Forces a state for the component gallery (`hover` / `focus`). */
  "data-force"?: string;
};

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  disabled,
  type = "button",
  className,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      aria-busy={loading || undefined}
      className={buttonClasses(variant, size, className)}
      disabled={disabled || loading}
      type={type}
    >
      {loading && <Spinner />}
      {children}
    </button>
  );
}

export type IconButtonProps = Omit<ButtonProps, "children" | "aria-label"> & {
  /** Required: an icon alone has no accessible name (WCAG 4.1.2). */
  label: string;
  icon: ReactNode;
};

/** Square icon-only button: 44×44 by default, 36×36 at `sm`. */
export function IconButton({ label, icon, size = "touch", variant = "ghost", className, ...rest }: IconButtonProps) {
  return (
    <Button
      {...rest}
      aria-label={label}
      className={cx(size === "sm" ? "size-9 px-0" : "size-11 px-0", className)}
      size={size}
      title={label}
      variant={variant}
    >
      <span aria-hidden="true" className="inline-flex size-5 items-center justify-center">
        {icon}
      </span>
    </Button>
  );
}
