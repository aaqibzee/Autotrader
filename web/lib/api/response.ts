import { toApiError } from "./error";
import { createApiHeaders } from "./headers";

async function readBody(response: Response): Promise<unknown> {
	const text = await response.text();
	if (!text) return undefined;

	try {
		return JSON.parse(text) as unknown;
	} catch {
		return text;
	}
}

export async function requestApi<TResponse = unknown>(
	input: RequestInfo | URL,
	init: RequestInit = {},
): Promise<TResponse> {
	const response = await fetch(input, {
		...init,
		headers: createApiHeaders(init.headers),
		cache: init.cache ?? "no-store",
		credentials: init.credentials ?? "same-origin",
	});
	const body = await readBody(response);

	if (!response.ok) {
		throw toApiError(body, response.status, response.headers.get("x-request-id") ?? undefined);
	}

	if (response.status === 204 || body === undefined) return undefined as TResponse;
	if (typeof body === "string") {
		throw new Error("The API returned a non-JSON success response");
	}

	return body as TResponse;
}
