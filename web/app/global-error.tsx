"use client";

import * as Sentry from "@sentry/nextjs";
import { useEffect } from "react";

/**
 * Last-resort boundary for errors thrown by the root layout itself. It replaces the
 * whole document, so it renders its own <html>/<body> and relies on no app styles.
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
      <body style={{ fontFamily: "system-ui, sans-serif", margin: 0, padding: "4rem 1.5rem" }}>
        <main style={{ maxWidth: "40rem", margin: "0 auto" }}>
          <h1 style={{ fontSize: "2rem", margin: 0 }}>We could not load this page.</h1>
          <p style={{ color: "#4a5551" }}>Please try again in a moment.</p>
          <button onClick={reset} type="button" style={{ padding: "0.5rem 1rem" }}>
            Try again
          </button>
          {error.digest && (
            <p style={{ fontFamily: "monospace", fontSize: "0.75rem", color: "#4a5551" }}>
              Reference: {error.digest}
            </p>
          )}
        </main>
      </body>
    </html>
  );
}
