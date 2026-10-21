import {
  PERMISSION_UI,
  PROBLEM_UI,
  type ProblemUi,
} from "@/lib/api/problem-ui";
import type { ReactNode } from "react";
import { Button } from "./button";
import { cx } from "./cx";

/**
 * What a screen shows instead of content (Feature 03 §4): nothing to show, or something
 * went wrong. No screen ends in a raw error or an endless spinner.
 *
 * Hook-free, so they render in server components too. Error copy comes from
 * `problem-ui.ts`, never from the caller; the caller supplies only actions.
 * `data-problem-kind` names which state rendered, for tests and support screenshots.
 */
type HeadingLevel = 2 | 3;

function StateFrame({
  tone,
  icon,
  title,
  message,
  headingLevel = 2,
  children,
  className,
  kind,
}: {
  tone: "neutral" | "danger" | "warning" | "info";
  icon: ReactNode;
  title: ReactNode;
  message: ReactNode;
  headingLevel?: HeadingLevel;
  children?: ReactNode;
  className?: string;
  kind: string;
}) {
  const Heading = `h${headingLevel}` as const;
  return (
    <section
      className={cx(
        "flex flex-col items-center gap-3 rounded-lg border border-line bg-surface px-6 py-10 text-center",
        className,
      )}
      data-problem-kind={kind}
    >
      <span
        aria-hidden="true"
        className={cx(
          "flex size-12 items-center justify-center rounded-full",
          {
            neutral: "bg-sunken text-ink-muted",
            danger: "bg-danger-tint text-danger",
            warning: "bg-warning-tint text-warning",
            info: "bg-info-tint text-info",
          }[tone],
        )}
      >
        {icon}
      </span>
      <Heading className="text-lg font-semibold text-ink">{title}</Heading>
      <p className="max-w-prose text-ink-soft">{message}</p>
      {children}
    </section>
  );
}

const svg = (path: ReactNode) => (
  <svg
    className="size-6"
    fill="none"
    stroke="currentColor"
    strokeLinecap="round"
    strokeWidth="2"
    viewBox="0 0 24 24"
  >
    {path}
  </svg>
);
const ICONS = {
  search: svg(<path d="M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zm5-2 4 4" />),
  alert: svg(
    <path d="M12 8v5m0 3h.01M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />,
  ),
  plug: svg(<path d="M9 2v6m6-6v6M6 8h12v3a6 6 0 0 1-12 0V8zm6 9v5" />),
  offline: svg(
    <path d="M2 2l20 20M8.5 16.5a5 5 0 0 1 7 0M5 13a10 10 0 0 1 5.2-2.8M19 13a10 10 0 0 0-2-1.5M2 8.8a15 15 0 0 1 4.2-2.6M22 8.8A15 15 0 0 0 11 5M12 20h.01" />,
  ),
  lock: svg(<path d="M6 11V8a6 6 0 0 1 12 0v3M5 11h14v10H5z" />),
};

export function EmptyState({
  title,
  message,
  action,
  icon = ICONS.search,
  headingLevel,
  className,
}: {
  title: ReactNode;
  message: ReactNode;
  /** The one obvious next step, e.g. "Clear filters". */
  action?: ReactNode;
  icon?: ReactNode;
  headingLevel?: HeadingLevel;
  className?: string;
}) {
  return (
    <StateFrame
      className={className}
      headingLevel={headingLevel}
      icon={icon}
      kind="empty"
      message={message}
      title={title}
      tone="neutral"
    >
      {action ? <div className="mt-2">{action}</div> : null}
    </StateFrame>
  );
}

export type ErrorStateVariant = "generic" | "unavailable" | "offline";

const VARIANT_OF: Partial<Record<ProblemUi["kind"], ErrorStateVariant>> = {
  unavailable: "unavailable",
  offline: "offline",
};

export function errorStateVariant(ui: ProblemUi): ErrorStateVariant {
  return VARIANT_OF[ui.kind] ?? "generic";
}

/**
 * Something went wrong. The variant follows from `ui.kind`:
 * - `generic`: retry, plus the request id shown small for support.
 * - `unavailable`: an integration is down, and the feature carries on without it
 *   (`continueAction`, e.g. "Enter details manually"), Feature 03 §3.
 * - `offline`: no connection; entered values are kept.
 */
export function ErrorState({
  ui,
  requestId,
  onRetry,
  continueAction,
  action,
  headingLevel,
  className,
}: {
  ui: ProblemUi;
  requestId?: string;
  /** Shown only when `ui.retry` is true. */
  onRetry?: () => void;
  /** The "continue manually" path of the `unavailable` variant. */
  continueAction?: ReactNode;
  /** Any other action, e.g. a sign-in link for `sign-in`. */
  action?: ReactNode;
  headingLevel?: HeadingLevel;
  className?: string;
}) {
  const variant = errorStateVariant(ui);
  const showRetry = ui.retry && onRetry !== undefined;
  return (
    <StateFrame
      className={className}
      headingLevel={headingLevel}
      icon={
        {
          generic: ICONS.alert,
          unavailable: ICONS.plug,
          offline: ICONS.offline,
        }[variant]
      }
      kind={ui.kind}
      message={ui.message}
      title={ui.title}
      tone={
        { generic: "danger", unavailable: "warning", offline: "info" }[
          variant
        ] as "danger" | "warning" | "info"
      }
    >
      {showRetry || continueAction || action ? (
        <div className="mt-2 flex flex-wrap justify-center gap-3">
          {variant === "unavailable" ? continueAction : null}
          {action}
          {showRetry ? (
            <Button
              onClick={onRetry}
              variant={variant === "unavailable" ? "secondary" : "primary"}
            >
              Try again
            </Button>
          ) : null}
        </div>
      ) : null}
      {requestId ? (
        <p className="mt-2 font-mono text-xs text-ink-muted">
          Reference: <span className="select-all">{requestId}</span>
        </p>
      ) : null}
    </StateFrame>
  );
}

export function PermissionDenied({
  ui = PERMISSION_UI,
  action,
  headingLevel,
  className,
}: {
  /** A more specific permission problem, e.g. `dealer_not_approved` ("Awaiting approval"). */
  ui?: ProblemUi;
  action?: ReactNode;
  headingLevel?: HeadingLevel;
  className?: string;
}) {
  return (
    <StateFrame
      className={className}
      headingLevel={headingLevel}
      icon={ICONS.lock}
      kind={ui.kind}
      message={ui.message}
      title={ui.title}
      tone="neutral"
    >
      {action ? <div className="mt-2">{action}</div> : null}
    </StateFrame>
  );
}

/** In-page "not found" (a listing in a list, a panel). Whole-page 404s are 3.13's pages. */
export function NotFound({
  ui = PROBLEM_UI.not_found,
  action,
  headingLevel,
  className,
}: {
  ui?: ProblemUi;
  action?: ReactNode;
  headingLevel?: HeadingLevel;
  className?: string;
}) {
  return (
    <StateFrame
      className={className}
      headingLevel={headingLevel}
      icon={ICONS.search}
      kind={ui.kind}
      message={ui.message}
      title={ui.title}
      tone="neutral"
    >
      {action ? <div className="mt-2">{action}</div> : null}
    </StateFrame>
  );
}
