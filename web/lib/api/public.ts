import "server-only";
import { headers } from "next/headers";
import {
  CONTEXT_HEADERS,
  forwardedHeaders,
  requestInternalApi,
} from "./forwarding";
import type { ApiPath, ApiRequestOptions, ApiResponse } from "./types";

/**
 * The only API client for public routes (`app/(public)/**`). It never forwards the
 * visitor's cookie or authorization, so public HTML is identical for everyone and safe to
 * cache at the edge (Feature 03 §6, A4). Personal data belongs in client islands.
 */
export async function getPublicApi<Path extends ApiPath>(
  path: Path,
  options: ApiRequestOptions = {},
): Promise<ApiResponse<Path>> {
  const outgoing = forwardedHeaders(
    await headers(),
    CONTEXT_HEADERS,
    options.headers,
  );
  return requestInternalApi(path, outgoing, options);
}
