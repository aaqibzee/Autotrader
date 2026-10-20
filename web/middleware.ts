import { buildContentSecurityPolicy } from "@/lib/security/csp";
import { NextResponse, type NextRequest } from "next/server";

// Same rule as the API's RequestContextMiddleware, so an id accepted here is accepted there.
const REQUEST_ID = /^[A-Za-z0-9._:-]{1,128}$/;

export function middleware(request: NextRequest) {
  const nonce = btoa(crypto.randomUUID());
  const contentSecurityPolicy = buildContentSecurityPolicy({
    nonce,
    development: process.env.NODE_ENV === "development",
    imageCdnOrigin: process.env.IMAGE_CDN_ORIGIN,
    errorIngestOrigin: process.env.ERROR_INGEST_ORIGIN,
    uploadsBucketOrigin: process.env.UPLOADS_BUCKET_ORIGIN,
  });
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