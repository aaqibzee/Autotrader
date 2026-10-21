import { assertApiPath } from "./headers";
import { requestApi } from "./response";
import type {
  ApiMutationBody,
  ApiMutationOptions,
  ApiMutationPath,
  ApiMutationResponse,
  ApiPath,
  ApiRequestOptions,
  ApiResponse,
  MutationMethod,
} from "./types";

/** Browser calls give up after 10 s and show the error state with retry (Feature 03 §3). */
export const CLIENT_TIMEOUT_MS = 10_000;

export function getClientApi<Path extends ApiPath>(
  path: Path,
  options: ApiRequestOptions = {},
): Promise<ApiResponse<Path>> {
  assertApiPath(path);
  return requestApi<ApiResponse<Path>>(path, {
    ...options,
    timeoutMs: CLIENT_TIMEOUT_MS,
  });
}

/** POST/PUT/PATCH/DELETE with a typed JSON body and response (Feature 03 A7). */
export function mutateClientApi<
  M extends MutationMethod,
  Path extends ApiMutationPath<M>,
>(
  method: M,
  path: Path,
  body: ApiMutationBody<Path, M>,
  { idempotencyKey, ...options }: ApiMutationOptions = {},
): Promise<ApiMutationResponse<Path, M>> {
  assertApiPath(path);
  const headers = new Headers(options.headers);
  if (body !== undefined) headers.set("Content-Type", "application/json");
  if (idempotencyKey) headers.set("Idempotency-Key", idempotencyKey);
  return requestApi<ApiMutationResponse<Path, M>>(path, {
    ...options,
    method: method.toUpperCase(),
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    timeoutMs: CLIENT_TIMEOUT_MS,
  });
}
