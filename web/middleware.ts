import { NextResponse, type NextRequest } from "next/server";

function configuredOrigin(value: string | undefined): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    if (url.protocol !== "https:" && url.hostname !== "localhost" && url.hostname !== "127.0.0.1") {
      return undefined;
    }
    return url.origin;
  } catch {
    return undefined;
  }
}

function buildContentSecurityPolicy(nonce: string): string {
  const imageCdn = configuredOrigin(process.env.IMAGE_CDN_ORIGIN);
  const errorIngest = configuredOrigin(process.env.ERROR_INGEST_ORIGIN);
  const uploadsBucket = configuredOrigin(process.env.UPLOADS_BUCKET_ORIGIN);
  const scriptSources = ["'self'", `'nonce-${nonce}'`, "'strict-dynamic'"];
  if (process.env.NODE_ENV === "development") scriptSources.push("'unsafe-eval'");

  return [
    "default-src 'self'",
    `script-src ${scriptSources.join(" ")}`,
    `style-src 'self' 'nonce-${nonce}'`,
    `img-src 'self' data: blob:${imageCdn ? ` ${imageCdn}` : ""}`,
    `connect-src 'self'${errorIngest ? ` ${errorIngest}` : ""}${uploadsBucket ? ` ${uploadsBucket}` : ""}`,
    "font-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}

// Same rule as the API's RequestContextMiddleware, so an id accepted here is accepted there.
const REQUEST_ID = /^[A-Za-z0-9._:-]{1,128}$/;

export function middleware(request: NextRequest) {
  const nonce = btoa(crypto.randomUUID());
  const contentSecurityPolicy = buildContentSecurityPolicy(nonce);
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", contentSecurityPolicy);

  // One id per page render, forwarded on SSR -> API calls (lib/api/server.ts) and tagged on
  // error reports, so a broken page can be traced through the API logs.
  const incomingId = request.headers.get("x-request-id");
  const requestId = incomingId && REQUEST_ID.test(incomingId) ? incomingId : crypto.randomUUID();
  requestHeaders.set("x-request-id", requestId);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", contentSecurityPolicy);
  response.headers.set("X-Request-ID", requestId);
  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};