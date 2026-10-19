import type { components } from "./schema";

export type ApiValidationError = components["schemas"]["ProblemValidationError"];
export type ProblemDetails = Partial<components["schemas"]["ProblemDetails"]>;

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readValidationErrors(value: unknown): ApiValidationError[] | undefined {
	if (!Array.isArray(value)) return undefined;

	const errors = value.flatMap((entry): ApiValidationError[] => {
		if (!isRecord(entry)) return [];
		if (
			typeof entry.field !== "string" ||
			typeof entry.code !== "string" ||
			typeof entry.message !== "string"
		) {
			return [];
		}
		return [{ field: entry.field, code: entry.code, message: entry.message }];
	});

	return errors.length > 0 ? errors : undefined;
}

export class ApiError extends Error {
	readonly type: string;
	readonly status: number;
	readonly detail?: string;
	readonly code?: string;
	readonly requestId?: string;
	readonly errors?: ApiValidationError[];

	constructor(problem: ProblemDetails, status: number, requestId?: string) {
		super(problem.title || `HTTP ${status}`);
		this.name = "ApiError";
		this.type = problem.type || "about:blank";
		this.status = status;
		this.detail = problem.detail;
		this.code = problem.code;
		this.requestId = problem.request_id || requestId;
		this.errors = problem.errors ?? undefined;
	}
}

export function toApiError(
	body: unknown,
	status: number,
	responseRequestId?: string,
): ApiError {
	if (!isRecord(body)) {
		return new ApiError({}, status, responseRequestId);
	}

	const problem: ProblemDetails = {
		type: typeof body.type === "string" ? body.type : undefined,
		title: typeof body.title === "string" ? body.title : undefined,
		status: typeof body.status === "number" ? body.status : undefined,
		detail: typeof body.detail === "string" ? body.detail : undefined,
		instance: typeof body.instance === "string" ? body.instance : undefined,
		code: typeof body.code === "string" ? body.code : undefined,
		request_id: typeof body.request_id === "string" ? body.request_id : undefined,
		errors: readValidationErrors(body.errors),
	};

	return new ApiError(problem, status, responseRequestId);
}
