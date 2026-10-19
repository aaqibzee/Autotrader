import { afterEach, describe, expect, it, vi } from "vitest";
import { getClientApi } from "./client";
import { ApiError } from "./error";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("client API boundary", () => {
  it("rejects paths that could escape the same-origin API route", () => {
    expect(() => getClientApi("https://example.com/api/v1/health" as never)).toThrow(
      "API paths must be same-origin /api/v1 routes",
    );
    expect(() => getClientApi("/api/v1/../admin" as never)).toThrow(
      "API paths must be same-origin /api/v1 routes",
    );
  });

  it("converts non-2xx Problem Details responses to ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            type: "about:blank",
            title: "Conflict",
            status: 409,
            code: "stale_update",
            request_id: "req-123",
          }),
          { status: 409, headers: { "content-type": "application/problem+json" } },
        ),
      ),
    );

    await expect(getClientApi("/api/v1/health/live")).rejects.toMatchObject({
      name: "ApiError",
      message: "Conflict",
      status: 409,
      code: "stale_update",
      requestId: "req-123",
    } satisfies Partial<ApiError>);
  });
});