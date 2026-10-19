import * as Sentry from "@sentry/nextjs";
import { sentryOptions } from "@/lib/observability/sentry-options";

export function register() {
	// Same options for the Node.js (SSR) and edge (middleware) runtimes.
	Sentry.init(sentryOptions(process.env.SENTRY_DSN));
}

/** Reports server-component, route-handler and middleware errors, tagged for correlation. */
export const onRequestError: typeof Sentry.captureRequestError = (error, request, context) => {
	const requestId = request.headers["x-request-id"];
	Sentry.withScope((scope) => {
		if (typeof requestId === "string") scope.setTag("request_id", requestId);
		Sentry.captureRequestError(error, request, context);
	});
};
