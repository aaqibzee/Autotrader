import type { ApiPath } from "./types";

export function assertApiPath(path: string): asserts path is ApiPath {
	let normalizedPath: string;
	try {
		normalizedPath = new URL(path, "http://same-origin.invalid").pathname;
	} catch {
		throw new TypeError("API paths must be same-origin /api/v1 routes");
	}

	if (
		!path.startsWith("/api/v1/") ||
		path.startsWith("//") ||
		path.includes("\\") ||
		!normalizedPath.startsWith("/api/v1/")
	) {
		throw new TypeError("API paths must be same-origin /api/v1 routes");
	}
}

export function createApiHeaders(headers?: HeadersInit): Headers {
	const result = new Headers(headers);
	result.set("Accept", "application/json, application/problem+json");
	return result;
}
