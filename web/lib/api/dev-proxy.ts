import "server-only";

/**
 * Same-origin `/api/v1/*` for e2e and local `next dev`, where no nginx sits in front
 * (Feature 03 slice 3.10). In every deployed environment nginx sends `/api/` to the API
 * before Next sees it, so this never runs there. It is also off unless
 * `DEV_API_PROXY=1` is set at runtime, so a misrouted request gets a 404, not a proxy.
 *
 * It forwards only what the browser API client sends and reads: it is a test harness,
 * not a general proxy.
 */
const REQUEST_HEADERS = [
  "accept",
  "content-type",
  "cookie",
  "idempotency-key",
  "x-request-id",
] as const;
const RESPONSE_HEADERS = [
  "content-type",
  "idempotent-replayed",
  "retry-after",
  "set-cookie",
  "x-request-id",
] as const;

export function devApiProxyEnabled(
  env: Readonly<Record<string, string | undefined>> = process.env,
): boolean {
  return env.DEV_API_PROXY === "1";
}

export async function proxyToApi(request: Request): Promise<Response> {
  if (!devApiProxyEnabled()) {
    return new Response(null, { status: 404 });
  }
  const url = new URL(request.url);
  const origin = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
  const headers = new Headers();
  for (const name of REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value !== null) headers.set(name, value);
  }
  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  const upstream = await fetch(`${origin}${url.pathname}${url.search}`, {
    method: request.method,
    headers,
    body: hasBody ? await request.arrayBuffer() : undefined,
    cache: "no-store",
    redirect: "manual",
    // A browser that gives up (timeout, navigation) cancels the upstream call too.
    signal: request.signal,
  });
  const responseHeaders = new Headers();
  for (const name of RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value !== null) responseHeaders.set(name, value);
  }
  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}
