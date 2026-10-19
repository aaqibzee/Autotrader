import { headers } from "next/headers";
import { assertApiPath } from "./headers";
import { requestApi } from "./response";
import type { ApiPath, ApiRequestOptions, ApiResponse } from "./types";

const FORWARDED_HEADERS = [
	"cookie",
	"x-request-id",
	"x-verified-cloudflare-peer",
	"x-forwarded-for",
	"cf-connecting-ip",
	"x-real-ip",
	"traceparent",
	"tracestate",
	"baggage",
] as const;

export async function getServerApi<Path extends ApiPath>(
	path: Path,
	options: ApiRequestOptions = {},
): Promise<ApiResponse<Path>> {
	assertApiPath(path);

	const incomingHeaders = await headers();
	const outgoingHeaders = new Headers(options.headers);
	for (const name of FORWARDED_HEADERS) {
		const value = incomingHeaders.get(name);
		if (value) outgoingHeaders.set(name, value);
	}

	const apiOrigin = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
	const url = new URL(path, apiOrigin);
	return requestApi<ApiResponse<Path>>(url, {
		...options,
		headers: outgoingHeaders,
		signal: options.signal ?? AbortSignal.timeout(3_000),
	});
}
