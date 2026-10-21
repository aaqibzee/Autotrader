import { describe, expect, it } from "vitest";
import { ApiError, ApiNetworkError, ApiTimeoutError, parseRetryAfter, toApiError } from "./error";

describe("RFC 9457 API errors", () => {
  it("retains stable problem fields and validation errors", () => {
    const error = toApiError(
      {
        type: "https://autotrader.example/problems/invalid-request",
        title: "Invalid request",
        status: 422,
        detail: "Check the highlighted fields.",
        code: "validation_failed",
        request_id: "req-body",
        errors: [{ field: "vrm", code: "invalid_format", message: "Enter a valid VRM." }],
      },
      422,
    );

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      type: "https://autotrader.example/problems/invalid-request",
      message: "Invalid request",
      status: 422,
      detail: "Check the highlighted fields.",
      code: "validation_failed",
      requestId: "req-body",
      errors: [{ field: "vrm", code: "invalid_format", message: "Enter a valid VRM." }],
    });
  });

  it("uses safe defaults for malformed problem bodies and response request ids", () => {
    const error = toApiError("upstream returned HTML", 502, "req-header");

    expect(error).toMatchObject({ message: "HTTP 502", status: 502, type: "about:blank", requestId: "req-header" });
    expect(error.detail).toBeUndefined();
    expect(error.errors).toBeUndefined();
  });

  it("ignores malformed validation entries", () => {
    const error = toApiError({ title: "Invalid", errors: [{ field: "vrm" }] }, 400);
    expect(error.errors).toBeUndefined();
  });
});
describe("Retry-After and extension members (Feature 03 A6)", () => {
  it("keeps extension members such as `current` on a 409", () => {
    const current = { title: "2019 Ford Fiesta", updated_at: "2026-10-21T10:00:00Z" };
    const error = toApiError({ title: "Conflict", code: "stale_update", current }, 409);
    expect(error.extensions).toEqual({ current });
    expect(error.code).toBe("stale_update");
  });

  it("has no extensions for a body with only standard members, or no body", () => {
    expect(toApiError({ title: "x", status: 400, code: "bad_request" }, 400).extensions).toEqual({});
    expect(toApiError(undefined, 500).extensions).toEqual({});
  });

  it("reads Retry-After from the header, also for a non-JSON body", () => {
    expect(toApiError({ code: "rate_limited" }, 429, undefined, "30").retryAfterSeconds).toBe(30);
    expect(toApiError("<html>", 503, undefined, "5").retryAfterSeconds).toBe(5);
    expect(toApiError({}, 429).retryAfterSeconds).toBeUndefined();
  });
});

describe("parseRetryAfter", () => {
  const now = Date.parse("2026-10-21T10:00:00Z");

  it.each([
    ["0", 0],
    ["30", 30],
    [" 120 ", 120],
    ["3600", 3600],
    ["Wed, 21 Oct 2026 10:01:30 GMT", 90],
    ["Wed, 21 Oct 2026 09:59:00 GMT", 0],
  ])("%j -> %j", (value, expected) => {
    expect(parseRetryAfter(value, now)).toBe(expected);
  });

  it.each([null, undefined, "", "soon", "-5", "1.5", "3601", "Wed, 21 Oct 2026 12:00:00 GMT"])(
    "%j -> undefined",
    (value) => {
      expect(parseRetryAfter(value, now)).toBeUndefined();
    },
  );

  it("uses the current time by default", () => {
    expect(parseRetryAfter(new Date(Date.now() + 10_500).toUTCString())).toBeGreaterThanOrEqual(9);
  });
});

describe("error classes", () => {
  it("name themselves and keep the cause", () => {
    const cause = new TypeError("fetch failed");
    expect(new ApiNetworkError(cause)).toMatchObject({ name: "ApiNetworkError", cause });
    expect(new ApiTimeoutError(10_000)).toMatchObject({
      name: "ApiTimeoutError",
      timeoutMs: 10_000,
      message: "The request took longer than 10 s",
    });
  });
});
