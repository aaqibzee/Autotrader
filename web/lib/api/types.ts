import type { paths } from "./schema";

/**
 * Types for calling the API, derived from the generated OpenAPI contract (Feature 01 §5).
 * Every type takes the paths interface as a last parameter (default: the real one), so the
 * method-aware helpers can be tested against a fixture contract (types.test.ts) before the
 * API has any mutation endpoints.
 */
export type HttpMethod = "get" | "post" | "put" | "patch" | "delete";
export type MutationMethod = Exclude<HttpMethod, "get">;

/**
 * Paths under /api/v1 that define `method`. openapi-typescript writes an absent method as
 * an optional `never` member, which `Record<M, unknown>` (a required member) excludes.
 */
export type PathFor<M extends HttpMethod, P = paths> = {
	[K in keyof P]: K extends `/api/v1/${string}` ? (P[K] extends Record<M, unknown> ? K : never) : never;
}[keyof P];

export type OperationFor<Path, M extends HttpMethod, P = paths> = Path extends keyof P
	? P[Path] extends Record<M, infer Operation>
		? Operation
		: never
	: never;

type JsonBody<Response> = Response extends {
	content: { "application/json": infer Body };
}
	? Body
	: never;

type SuccessfulJsonResponse<Operation> = Operation extends {
	responses: infer Responses;
}
	? {
			[Status in keyof Responses]: Status extends 200 | 201 | 202 | 203 | 204
				? JsonBody<Responses[Status]>
				: never;
		}[keyof Responses]
	: never;

/** The JSON request body an operation takes, or `undefined` when it takes none. */
export type RequestBodyOf<Operation> = Operation extends { requestBody?: infer RequestBody }
	? RequestBody extends { content: { "application/json": infer Body } }
		? Body
		: undefined
	: undefined;

export type ApiPath<P = paths> = PathFor<"get", P>;
export type ApiResponse<Path, P = paths> = SuccessfulJsonResponse<OperationFor<Path, "get", P>>;

export type ApiMutationPath<M extends MutationMethod, P = paths> = PathFor<M, P>;
export type ApiMutationBody<Path, M extends MutationMethod, P = paths> = RequestBodyOf<
	OperationFor<Path, M, P>
>;
export type ApiMutationResponse<Path, M extends MutationMethod, P = paths> = SuccessfulJsonResponse<
	OperationFor<Path, M, P>
>;

export type ApiRequestOptions = Omit<RequestInit, "headers" | "body" | "method"> & {
	headers?: HeadersInit;
};

export type ApiMutationOptions = ApiRequestOptions & {
	/**
	 * Sent as `Idempotency-Key` (Feature 01 §5), for the side-effecting POSTs a client may
	 * retry. `useApiForm` generates one per form and reuses it on retry (slice 3.10).
	 */
	idempotencyKey?: string;
};
