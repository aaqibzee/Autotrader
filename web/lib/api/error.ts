import type { components } from "./schema";

export type ApiValidationError = components["schemas"]["ProblemValidationError"];
export type ProblemCode = components["schemas"]["ProblemCode"];
/**
 * A problem body as received. `code` stays a plain string here: a newer API may send a
 * code this build does not know yet, and the UI must still fall back by status
 * (lib/api/problem-ui.ts).
 */
export type ProblemDetails = {
	type?: string;
	title?: string;
	status?: number;
	detail?: string;
	instance?: string;
	code?: string;
	request_id?: string | null;
	errors?: ApiValidationError[] | null;
};

/** RFC 9457 members; anything else in a problem body is an extension member. */
const STANDARD_MEMBERS = new Set([
	"type",
	"title",
	"status",
	"detail",
	"instance",
	"code",
	"request_id",
	"errors",
]);

/** A server asking for a longer wait than this is ignored; the UI never counts down an hour. */
export const MAX_RETRY_AFTER_SECONDS = 3_600;
// RFC 9110 IMF-fixdate, e.g. `Wed, 21 Oct 2026 07:28:00 GMT`. Matched before `Date.parse`,
// which would otherwise accept "-5" (the year -5) or "1.5" as dates.
const HTTP_DATE = /^[A-Z][a-z]{2}, \d{2} [A-Z][a-z]{2} \d{4} \d{2}:\d{2}:\d{2} GMT$/;

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

/**
 * `Retry-After` as whole seconds from now (RFC 9110 §10.2.3): delta-seconds or an
 * HTTP-date. Undefined when absent, unparseable or over the cap; never negative.
 */
export function parseRetryAfter(
	value: string | null | undefined,
	now: number = Date.now(),
): number | undefined {
	if (!value) return undefined;
	const trimmed = value.trim();
	let seconds: number;
	if (/^\d+$/.test(trimmed)) {
		seconds = Number(trimmed);
	} else {
		const at = HTTP_DATE.test(trimmed) ? Date.parse(trimmed) : Number.NaN;
		if (Number.isNaN(at)) return undefined;
		seconds = Math.max(0, Math.ceil((at - now) / 1_000));
	}
	return seconds <= MAX_RETRY_AFTER_SECONDS ? seconds : undefined;
}

export type ApiErrorOptions = {
	retryAfterSeconds?: number;
	extensions?: Record<string, unknown>;
};

/** The API answered with a non-2xx Problem Details response. */
export class ApiError extends Error {
	readonly type: string;
	readonly status: number;
	readonly detail?: string;
	readonly code?: string;
	readonly requestId?: string;
	readonly errors?: ApiValidationError[];
	/** From the `Retry-After` header (429, 503). */
	readonly retryAfterSeconds?: number;
	/** Extension members, e.g. `current` on a 409 `stale_update` (Feature 03 A6). */
	readonly extensions: Readonly<Record<string, unknown>>;

	constructor(
		problem: ProblemDetails,
		status: number,
		requestId?: string,
		options: ApiErrorOptions = {},
	) {
		super(problem.title || `HTTP ${status}`);
		this.name = "ApiError";
		this.type = problem.type || "about:blank";
		this.status = status;
		this.detail = problem.detail;
		this.code = problem.code;
		this.requestId = problem.request_id || requestId;
		this.errors = problem.errors ?? undefined;
		this.retryAfterSeconds = options.retryAfterSeconds;
		this.extensions = options.extensions ?? {};
	}
}

/** No response within the client's time limit (10 s in the browser, 3 s during SSR). */
export class ApiTimeoutError extends Error {
	readonly timeoutMs: number;

	constructor(timeoutMs: number) {
		super(`The request took longer than ${timeoutMs / 1_000} s`);
		this.name = "ApiTimeoutError";
		this.timeoutMs = timeoutMs;
	}
}

/** The request never got a response: offline, DNS, connection refused or reset. */
export class ApiNetworkError extends Error {
	constructor(cause: unknown) {
		super("The network request failed", { cause });
		this.name = "ApiNetworkError";
	}
}

export function toApiError(
	body: unknown,
	status: number,
	responseRequestId?: string,
	retryAfter?: string | null,
): ApiError {
	const retryAfterSeconds = parseRetryAfter(retryAfter);
	if (!isRecord(body)) {
		return new ApiError({}, status, responseRequestId, { retryAfterSeconds });
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
	const extensions = Object.fromEntries(
		Object.entries(body).filter(([key]) => !STANDARD_MEMBERS.has(key)),
	);

	return new ApiError(problem, status, responseRequestId, { retryAfterSeconds, extensions });
}
