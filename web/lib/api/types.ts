import type { paths } from "./schema";

export type ApiPath = Extract<keyof paths, `/api/v1/${string}`>;

type OperationFor<Path extends ApiPath> = paths[Path] extends { get: infer Operation }
	? Operation
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

export type ApiResponse<Path extends ApiPath> = SuccessfulJsonResponse<OperationFor<Path>>;

export type ApiRequestOptions = Omit<RequestInit, "headers"> & {
	headers?: HeadersInit;
};
