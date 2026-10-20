"use client";

import * as Sentry from "@sentry/nextjs";
import { useEffect } from "react";
import "./globals.css";

/**
 * Last-resort boundary for errors thrown by the root layout itself. It replaces the whole
 * document, so it renders its own <html>/<body> and imports the stylesheet itself. No
 * inline styles: an inline <style> element would be blocked by the CSP (Feature 03 A2).
 */
export default function GlobalError({
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
    <html lang="en-GB">
      <body className="font-sans">
        <main className="shell flex min-h-screen flex-col items-start justify-center">
          <h1 className="text-4xl font-semibold tracking-tight">We could not load this page.</h1>
          <p className="mt-3 text-ink-muted">Please try again in a moment.</p>
          <button
            className="mt-6 border border-ink px-4 py-2 text-sm font-semibold hover:bg-ink hover:text-surface"
            onClick={reset}
            type="button"
          >
            Try again
          </button>
          {error.digest && (
            <p className="mt-4 font-mono text-xs text-ink-muted">Reference: {error.digest}</p>
          )}
        </main>
      </body>
    </html>
  );
}
