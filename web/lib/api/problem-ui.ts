import {
  ApiError,
  ApiNetworkError,
  ApiTimeoutError,
  type ProblemCode,
} from "./error";

/**
 * Every API failure has exactly one UI, decided here (Feature 03 §3, A5). Components never
 * branch on status codes or problem codes themselves: they call `problemUi(error)` and
 * render its `kind`. All user-facing error copy lives in this file (design §10), so it can
 * be reviewed in one place.
 */
export type ProblemUiKind =
  /** Show `ApiError.errors` on their fields (useApiForm, slice 3.10). */
  | "field-errors"
  /** Open `ConflictDialog` with `extensions.current` (slice 3.10). */
  | "conflict"
  /** Inline message with a `Retry-After` countdown; never a toast (slice 3.9). */
  | "rate-limited"
  /** `ErrorState` "unavailable": the feature carries on without the integration. */
  | "unavailable"
  /** Redirect to sign-in with `safeNextPath` (Feature 04). */
  | "sign-in"
  | "permission"
  | "not-found"
  /** The request was wrong in a way the user cannot fix by retrying. */
  | "invalid"
  /** `ErrorState` with a retry button and the request id. */
  | "retryable"
  | "timeout"
  | "offline";

export type ProblemUi = {
  kind: ProblemUiKind;
  title: string;
  message: string;
  /** Whether a retry button makes sense. */
  retry: boolean;
};

export type ResolvedProblemUi = ProblemUi & {
  requestId?: string;
  retryAfterSeconds?: number;
};

const TRY_AGAIN = "Please try again in a moment.";

/**
 * One entry per backend `ProblemCode`. The `Record` type is the contract: a code added to
 * the API without an entry here fails `npm run typecheck`.
 */
export const PROBLEM_UI: Record<ProblemCode, ProblemUi> = {
  bad_request: {
    kind: "invalid",
    title: "That did not work",
    message:
      "Something about that request was not right. Please go back and try again.",
    retry: false,
  },
  not_found: {
    kind: "not-found",
    title: "We cannot find that",
    message: "It may have been removed, or the link may be wrong.",
    retry: false,
  },
  invalid_input: {
    kind: "field-errors",
    title: "Check the highlighted fields",
    message: "Some of the details need correcting before you can continue.",
    retry: false,
  },
  stale_update: {
    kind: "conflict",
    title: "This was changed by someone else",
    message:
      "Someone saved a newer version while you were editing. Choose which version to keep.",
    retry: false,
  },
  idempotency_key_reused: {
    kind: "invalid",
    title: "That did not go through",
    message:
      "The request changed while it was being retried. Please submit it again.",
    retry: false,
  },
  idempotency_in_progress: {
    kind: "retryable",
    title: "Still working on it",
    message:
      "Your previous request is still being processed. Wait a moment, then check before trying again.",
    retry: true,
  },
  invalid_cursor: {
    kind: "invalid",
    title: "These results have expired",
    message: "Go back to the first page of results and try again.",
    retry: false,
  },
  dealer_not_approved: {
    kind: "permission",
    title: "Awaiting approval",
    message:
      "You can create drafts while we review your dealership, but you cannot publish yet.",
    retry: false,
  },
  page_limit_exceeded: {
    kind: "invalid",
    title: "Too many pages",
    message: "Narrow your search with filters to see more results.",
    retry: false,
  },
  dependency_unavailable: {
    kind: "retryable",
    title: "Temporarily unavailable",
    message: `This service is not responding right now. ${TRY_AGAIN}`,
    retry: true,
  },
  rate_limited: {
    kind: "rate-limited",
    title: "Too many attempts",
    message: "Please wait before trying again.",
    retry: true,
  },
  integration_unavailable: {
    kind: "unavailable",
    title: "Lookup unavailable",
    message:
      "This lookup is not working right now. You can carry on and enter the details yourself.",
    retry: true,
  },
  internal_error: {
    kind: "retryable",
    title: "Something went wrong",
    message: `Something went wrong on our side. ${TRY_AGAIN}`,
    retry: true,
  },
};

/**
 * Codes the API uses for "no more specific code" (a bare HTTPException). For these the
 * status decides: a 403 raised that way is a permission problem, not a bad request.
 */
const GENERIC_CODES: ReadonlySet<string> = new Set<ProblemCode>([
  "bad_request",
  "internal_error",
]);

const STATUS_UI: Record<number, ProblemUi> = {
  401: {
    kind: "sign-in",
    title: "Please sign in",
    message: "Your session has ended. Sign in to carry on where you left off.",
    retry: false,
  },
  403: {
    kind: "permission",
    title: "You do not have access",
    message: "Your account does not have permission to do this.",
    retry: false,
  },
  404: PROBLEM_UI.not_found,
  409: PROBLEM_UI.stale_update,
  422: PROBLEM_UI.invalid_input,
  429: PROBLEM_UI.rate_limited,
  503: PROBLEM_UI.dependency_unavailable,
};

export const TIMEOUT_UI: ProblemUi = {
  kind: "timeout",
  title: "This is taking too long",
  message: `We did not get a response in time. ${TRY_AGAIN}`,
  retry: true,
};

export const OFFLINE_UI: ProblemUi = {
  kind: "offline",
  title: "You appear to be offline",
  message: "Check your connection. Anything you entered has been kept.",
  retry: true,
};

function isProblemCode(code: string | undefined): code is ProblemCode {
  return code !== undefined && Object.hasOwn(PROBLEM_UI, code);
}

function forStatus(status: number): ProblemUi {
  return (
    STATUS_UI[status] ??
    (status >= 500 ? PROBLEM_UI.internal_error : PROBLEM_UI.bad_request)
  );
}

/** The UI for anything a request can throw. Unknown errors are treated as retryable. */
export function problemUi(error: unknown): ResolvedProblemUi {
  if (error instanceof ApiTimeoutError) return TIMEOUT_UI;
  if (error instanceof ApiNetworkError) return OFFLINE_UI;
  if (!(error instanceof ApiError)) return PROBLEM_UI.internal_error;

  // A code this build does not know yet (newer API) falls back to its status.
  const ui =
    isProblemCode(error.code) && !GENERIC_CODES.has(error.code)
      ? PROBLEM_UI[error.code]
      : forStatus(error.status);
  return {
    ...ui,
    requestId: error.requestId,
    retryAfterSeconds: error.retryAfterSeconds,
  };
}
