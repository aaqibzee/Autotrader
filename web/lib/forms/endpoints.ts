/**
 * Every endpoint that accepts an `Idempotency-Key`, in one place (Feature 03 slice 3.10).
 * `useApiForm` sends a key only when given one of these names, so a form cannot claim
 * retry safety for an endpoint that was never reviewed for it. Later features add their
 * side-effecting POSTs here (lead submit, publish, invite).
 */
export const IDEMPOTENT_ENDPOINTS = {
  /** Dev-only probe for the e2e suite (backend endpoints/dev.py). */
  formProbe: "POST /api/v1/dev/form-probe/{probe_id}",
} as const;

export type IdempotentEndpoint = keyof typeof IDEMPOTENT_ENDPOINTS;
