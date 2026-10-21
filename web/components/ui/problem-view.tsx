"use client";

import { formatCountdown } from "@/lib/format";
import { type ProblemUi, problemUi } from "@/lib/api/problem-ui";
import { useRetryAfter } from "@/lib/hooks/use-retry-after";
import type { ReactNode } from "react";
import { Button } from "./button";
import { ErrorState, NotFound, PermissionDenied } from "./states";

/**
 * The right state for anything a request can throw (Feature 03 §3): an `ApiError`, a
 * timeout, a network failure or an unknown error. The decision is `problemUi`'s (3.5);
 * this only maps its `kind` to a component, so a screen never branches on status codes.
 *
 * Form kinds (`field-errors`, `conflict`) belong to `useApiForm` (3.10). If one reaches
 * here, it renders as a plain error without a retry.
 */
export function ProblemView({
  error,
  onRetry,
  continueAction,
  signInAction,
  headingLevel,
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  /** The `unavailable` variant's way to carry on without the integration. */
  continueAction?: ReactNode;
  /** A sign-in link for 401s (Feature 04 supplies it, with `safeNextPath`). */
  signInAction?: ReactNode;
  headingLevel?: 2 | 3;
  className?: string;
}) {
  const ui = problemUi(error);
  const shared = { headingLevel, className };
  switch (ui.kind) {
    case "permission":
      // The resolved copy, not the default: `dealer_not_approved` is "Awaiting approval".
      return <PermissionDenied {...shared} ui={ui} />;
    case "not-found":
      return <NotFound {...shared} ui={ui} />;
    case "rate-limited":
      return (
        <RateLimitNotice
          {...shared}
          onRetry={onRetry}
          resetKey={error}
          retryAfterSeconds={ui.retryAfterSeconds}
          ui={ui}
        />
      );
    case "sign-in":
      return <ErrorState {...shared} action={signInAction} ui={ui} />;
    default:
      return (
        <ErrorState
          {...shared}
          continueAction={continueAction}
          onRetry={onRetry}
          requestId={ui.requestId}
          ui={ui}
        />
      );
  }
}

/**
 * A 429: an inline message with the wait counted down, and retry enabled at zero. Never a
 * toast (design §3). One polite live region announces the start and the end only.
 */
export function RateLimitNotice({
  ui,
  retryAfterSeconds,
  resetKey,
  onRetry,
  headingLevel = 2,
  className,
}: {
  ui: ProblemUi;
  retryAfterSeconds?: number;
  resetKey?: unknown;
  onRetry?: () => void;
  headingLevel?: 2 | 3;
  className?: string;
}) {
  const { remaining, ready, announcement } = useRetryAfter(
    retryAfterSeconds,
    resetKey,
  );
  const Heading = `h${headingLevel}` as const;
  return (
    <section
      className={[
        "rounded-lg border border-warning bg-warning-tint px-5 py-4 text-warning",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      data-problem-kind={ui.kind}
    >
      <Heading className="font-semibold">{ui.title}</Heading>
      <p className="mt-1">
        {ui.message}
        {/* Visible every second, but outside the live region: not read out each tick. */}
        {ready ? null : (
          <>
            {" "}
            Try again in{" "}
            <span className="font-semibold tabular-nums">
              {formatCountdown(remaining)}
            </span>
            .
          </>
        )}
      </p>
      <p aria-live="polite" className="sr-only" role="status">
        {announcement}
      </p>
      {onRetry ? (
        <Button
          className="mt-3"
          disabled={!ready}
          onClick={onRetry}
          size="sm"
          variant="secondary"
        >
          Try again
        </Button>
      ) : null}
    </section>
  );
}
