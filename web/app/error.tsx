"use client";

import * as Sentry from "@sentry/nextjs";
import { useEffect } from "react";

export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <main className="shell flex min-h-screen flex-col items-start justify-center">
      <p className="font-mono text-xs uppercase tracking-[0.14em] text-ink-muted">
        Something went wrong
      </p>
      <h1 className="mt-3 text-4xl font-semibold tracking-tight">We could not load this page.</h1>
      <button
        className="mt-6 border border-ink px-4 py-2 text-sm font-semibold transition-colors hover:bg-ink hover:text-surface"
        onClick={reset}
        type="button"
      >
        Try again
      </button>
      {error.digest && (
        <p className="mt-4 font-mono text-xs text-ink-muted">Reference: {error.digest}</p>
      )}
    </main>
  );
}