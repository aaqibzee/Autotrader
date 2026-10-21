import { assertApiPath } from "./headers";
import { requestApi } from "./response";
import type { ApiPath, ApiRequestOptions, ApiResponse } from "./types";

/**
 * Headers an SSR -> API call may carry from the browser's request (Feature 01 §3).
 * Request id and trace context tie a page render to its API logs; the client-IP chain
 * lets the API's rate limits see the visitor, not the web server.
 */
export const CONTEXT_HEADERS = [
	"x-request-id",
	"x-verified-cloudflare-peer",
	"x-forwarded-for",
	"cf-connecting-ip",
	"x-real-ip",
	"traceparent",
	"tracestate",
	"baggage",
] as const;

/**
 * Headers that identify the visitor. Only the session client forwards them; a public page
 * that sent them would render one person's data into HTML the edge caches for everyone
 * (Feature 03 §6).
 */
export const IDENTITY_HEADERS = ["cookie", "authorization"] as const;

export function forwardedHeaders(
	incoming: Pick<Headers, "get">,
	names: readonly string[],
	base?: HeadersInit,
): Headers {
	const outgoing = new Headers(base);
	// A caller-supplied identity header would bypass the rule above, so it never survives.
	for (const name of IDENTITY_HEADERS) outgoing.delete(name);
	for (const name of names) {
		const value = incoming.get(name);
		if (value) outgoing.set(name, value);
	}
	return outgoing;
}

/** SSR request to the internal API URL with the given headers (Feature 03 §3). */
export const SERVER_TIMEOUT_MS = 3_000;

export function requestInternalApi<Path extends ApiPath>(
	path: Path,
	headers: Headers,
	options: ApiRequestOptions,
): Promise<ApiResponse<Path>> {
	assertApiPath(path);
	const apiOrigin = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
	return requestApi<ApiResponse<Path>>(new URL(path, apiOrigin), {
		...options,
		headers,
		timeoutMs: SERVER_TIMEOUT_MS,
	});
}
