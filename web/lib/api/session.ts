import "server-only";
import { headers } from "next/headers";
import {
  CONTEXT_HEADERS,
  IDENTITY_HEADERS,
  forwardedHeaders,
  requestInternalApi,
} from "./forwarding";
import type { ApiPath, ApiRequestOptions, ApiResponse } from "./types";

/**
 * API client for signed-in surfaces (`/dealer`, `/account`, `/admin`): forwards the
 * session cookie. Never reachable from `app/(public)/**`, directly or through any import
 * chain (ops/ci/check_web_boundaries.mjs, Feature 03 A4).
 */
export async function getSessionApi<Path extends ApiPath>(
  path: Path,
  options: ApiRequestOptions = {},
): Promise<ApiResponse<Path>> {
  const outgoing = forwardedHeaders(
    await headers(),
    [...IDENTITY_HEADERS, ...CONTEXT_HEADERS],
    options.headers,
  );
  return requestInternalApi(path, outgoing, options);
}
