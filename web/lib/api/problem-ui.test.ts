import { describe, expect, it } from "vitest";
import {
  ApiError,
  ApiNetworkError,
  ApiTimeoutError,
  type ProblemCode,
} from "./error";
import { OFFLINE_UI, PROBLEM_UI, TIMEOUT_UI, problemUi } from "./problem-ui";

function apiError(
  status: number,
  code?: string,
  extra: { retryAfterSeconds?: number } = {},
) {
  return new ApiError({ code, request_id: "req-1" }, status, undefined, extra);
}

describe("problemUi (Feature 03 §3)", () => {
  it.each<[number, ProblemCode, string]>([
    [422, "invalid_input", "field-errors"],
    [409, "stale_update", "conflict"],
    [429, "rate_limited", "rate-limited"],
    [503, "integration_unavailable", "unavailable"],
    [503, "dependency_unavailable", "retryable"],
    [403, "dealer_not_approved", "permission"],
    [404, "not_found", "not-found"],
    [409, "idempotency_in_progress", "retryable"],
    [422, "idempotency_key_reused", "invalid"],
    [400, "invalid_cursor", "invalid"],
    [400, "page_limit_exceeded", "invalid"],
  ])("%i %s -> %s", (status, code, kind) => {
    expect(problemUi(apiError(status, code)).kind).toBe(kind);
  });

  it("passes through the request id and Retry-After", () => {
    expect(
      problemUi(apiError(429, "rate_limited", { retryAfterSeconds: 30 })),
    ).toMatchObject({
      kind: "rate-limited",
      requestId: "req-1",
      retryAfterSeconds: 30,
    });
  });

  it("lets the status decide for the generic codes", () => {
    expect(problemUi(apiError(403, "bad_request")).kind).toBe("permission");
    expect(problemUi(apiError(401, "bad_request")).kind).toBe("sign-in");
    expect(problemUi(apiError(400, "bad_request")).kind).toBe("invalid");
    expect(problemUi(apiError(500, "internal_error")).kind).toBe("retryable");
  });

  it.each([
    [401, "sign-in"],
    [403, "permission"],
    [404, "not-found"],
    [409, "conflict"],
    [422, "field-errors"],
    [429, "rate-limited"],
    [503, "retryable"],
    [418, "invalid"],
    [502, "retryable"],
  ])(
    "falls back on status %i -> %s for an unknown or missing code",
    (status, kind) => {
      expect(problemUi(apiError(status, "code_from_a_newer_api")).kind).toBe(
        kind,
      );
      expect(problemUi(apiError(status)).kind).toBe(kind);
    },
  );

  it("does not treat inherited object keys as problem codes", () => {
    expect(problemUi(apiError(400, "toString")).kind).toBe("invalid");
  });

  it("maps timeouts, network failures and unknown throwables", () => {
    expect(problemUi(new ApiTimeoutError(10_000))).toBe(TIMEOUT_UI);
    expect(problemUi(new ApiNetworkError(new TypeError("fetch failed")))).toBe(
      OFFLINE_UI,
    );
    expect(problemUi(new Error("bug"))).toBe(PROBLEM_UI.internal_error);
    expect(problemUi("thrown string")).toBe(PROBLEM_UI.internal_error);
  });

  it("every entry has copy and a consistent retry flag", () => {
    for (const [code, ui] of Object.entries(PROBLEM_UI)) {
      expect(ui.title, code).not.toBe("");
      expect(ui.message, code).toMatch(/\.$/);
      if (ui.kind === "retryable" || ui.kind === "rate-limited")
        expect(ui.retry, code).toBe(true);
      if (ui.kind === "field-errors" || ui.kind === "not-found")
        expect(ui.retry, code).toBe(false);
    }
  });
});
