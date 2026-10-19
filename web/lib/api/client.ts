import { assertApiPath } from "./headers";
import { requestApi } from "./response";
import type { ApiPath, ApiRequestOptions, ApiResponse } from "./types";

export function getClientApi<Path extends ApiPath>(
	path: Path,
	options: ApiRequestOptions = {},
	): Promise<ApiResponse<Path>> {
	assertApiPath(path);
	return requestApi<ApiResponse<Path>>(path, options);
}
