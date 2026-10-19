import { describe, expect, it } from "vitest";
import { ApiError, toApiError } from "./error";

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