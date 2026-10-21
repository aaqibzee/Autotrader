import type { ErrorEvent } from "@sentry/nextjs";

/** Shared Sentry options for the browser, Node.js and edge runtimes. */
export function sentryOptions(dsn: string | undefined) {
  const environment =
    process.env.NEXT_PUBLIC_ENVIRONMENT ?? process.env.NODE_ENV;
  return {
    dsn: dsn || undefined,
    enabled: Boolean(dsn),
    environment,
    // UK GDPR: error reports are shipped to a third party, so never attach PII.
    sendDefaultPii: false,
    tracesSampleRate: environment === "production" ? 0.1 : 1.0,
    beforeSend: scrubEvent,
  };
}

export function scrubEvent(event: ErrorEvent): ErrorEvent {
  if (event.request) {
    delete event.request.cookies;
    delete event.request.data;
    delete event.request.query_string;
    if (event.request.headers) {
      const requestId = event.request.headers["x-request-id"];
      event.request.headers = requestId ? { "x-request-id": requestId } : {};
    }
    if (event.request.url) {
      // Keep the path for grouping, drop the query (may hold postcodes or VRMs).
      event.request.url = event.request.url.split("?")[0];
    }
  }
  delete event.user;
  return event;
}
