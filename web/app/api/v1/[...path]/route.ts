import { proxyToApi } from "@/lib/api/dev-proxy";

// e2e and local dev only (DEV_API_PROXY=1); nginx owns /api/ everywhere else.
export const dynamic = "force-dynamic";

export const GET = proxyToApi;
export const POST = proxyToApi;
export const PUT = proxyToApi;
export const PATCH = proxyToApi;
export const DELETE = proxyToApi;
