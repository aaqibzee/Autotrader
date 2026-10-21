import { reportNetworkFailure, reportNetworkSuccess } from "./connectivity";
import { ApiNetworkError, ApiTimeoutError, toApiError } from "./error";
import { createApiHeaders } from "./headers";

export type RequestApiInit = RequestInit & {
  /** Abort and throw `ApiTimeoutError` after this long. No spinner runs unbounded (Feature 03 §3). */
  timeoutMs?: number;
};

async function readBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return undefined;

  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

/**
 * The one place a request to our API is made. Failures come out as one of three types:
 * `ApiError` (the API answered non-2xx), `ApiTimeoutError` (our time limit) or
 * `ApiNetworkError` (no response at all). A caller's own abort is re-thrown unchanged, so
 * a cancelled request is never reported as a failure.
 */
export async function requestApi<TResponse = unknown>(
  input: RequestInfo | URL,
  init: RequestApiInit = {},
): Promise<TResponse> {
  const { timeoutMs, signal: callerSignal, ...rest } = init;
  const controller = new AbortController();
  let timedOut = false;
  const timer =
    timeoutMs === undefined
      ? undefined
      : setTimeout(() => {
          timedOut = true;
          controller.abort();
        }, timeoutMs);
  const forwardAbort = () => controller.abort(callerSignal?.reason);
  if (callerSignal?.aborted) forwardAbort();
  else callerSignal?.addEventListener("abort", forwardAbort, { once: true });

  let response: Response;
  let body: unknown;
  try {
    response = await fetch(input, {
      ...rest,
      signal: controller.signal,
      headers: createApiHeaders(rest.headers),
      cache: rest.cache ?? "no-store",
      credentials: rest.credentials ?? "same-origin",
    });
    // The body is read inside the time limit too: a stalled body is a hung request.
    body = await readBody(response);
  } catch (error) {
    if (timedOut) throw new ApiTimeoutError(timeoutMs!);
    if (callerSignal?.aborted) throw error;
    // No response at all: tell the offline banner (browser only; see connectivity.ts).
    reportNetworkFailure();
    throw new ApiNetworkError(error);
  } finally {
    clearTimeout(timer);
    callerSignal?.removeEventListener("abort", forwardAbort);
  }
  // Any response, even an error status, proves the network and the API are reachable.
  reportNetworkSuccess();

  if (!response.ok) {
    throw toApiError(
      body,
      response.status,
      response.headers.get("x-request-id") ?? undefined,
      response.headers.get("retry-after"),
    );
  }

  if (response.status === 204 || body === undefined)
    return undefined as TResponse;
  if (typeof body === "string") {
    throw new Error("The API returned a non-JSON success response");
  }

  return body as TResponse;
}
