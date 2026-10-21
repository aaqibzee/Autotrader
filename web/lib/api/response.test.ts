import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CLIENT_TIMEOUT_MS, getClientApi, mutateClientApi } from "./client";
import { isNetworkFailing, reportNetworkSuccess } from "./connectivity";
import { ApiError, ApiNetworkError, ApiTimeoutError } from "./error";
import { requestApi } from "./response";

// `fetch` is stubbed: these tests are about what the client does with a response it gets
// (or never gets). The real API is exercised by the e2e suite.
function respond(body: unknown, init: ResponseInit = {}) {
  return vi.fn(
    async () =>
      new Response(body === undefined ? null : JSON.stringify(body), {
        headers: { "content-type": "application/json" },
        ...init,
      }),
  );
}

/** A fetch that never answers, but rejects like the real one when its signal aborts. */
function hang() {
  return vi.fn(
    (_input: RequestInfo | URL, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        const abort = () =>
          reject(new DOMException("The operation was aborted.", "AbortError"));
        if (init?.signal?.aborted) abort();
        init?.signal?.addEventListener("abort", abort);
      }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  reportNetworkSuccess();
});

describe("client API boundary", () => {
  it("rejects paths that could escape the same-origin API route", () => {
    expect(() =>
      getClientApi("https://example.com/api/v1/health" as never),
    ).toThrow("API paths must be same-origin /api/v1 routes");
    expect(() => getClientApi("/api/v1/../admin" as never)).toThrow(
      "API paths must be same-origin /api/v1 routes",
    );
  });

  it("converts non-2xx Problem Details responses to ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      respond(
        {
          type: "about:blank",
          title: "Conflict",
          status: 409,
          code: "stale_update",
          request_id: "req-123",
        },
        {
          status: 409,
          headers: { "content-type": "application/problem+json" },
        },
      ),
    );

    await expect(getClientApi("/api/v1/health/ready")).rejects.toMatchObject({
      name: "ApiError",
      message: "Conflict",
      status: 409,
      code: "stale_update",
      requestId: "req-123",
    } satisfies Partial<ApiError>);
  });

  it("carries Retry-After and the response request id onto ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      respond(
        { title: "Too Many Requests", code: "rate_limited" },
        {
          status: 429,
          headers: { "retry-after": "42", "x-request-id": "req-hdr" },
        },
      ),
    );
    await expect(getClientApi("/api/v1/health/ready")).rejects.toMatchObject({
      status: 429,
      retryAfterSeconds: 42,
      requestId: "req-hdr",
    });
  });

  it("returns the JSON body, and undefined for 204", async () => {
    vi.stubGlobal("fetch", respond({ status: "ready" }));
    await expect(getClientApi("/api/v1/health/ready")).resolves.toEqual({
      status: "ready",
    });
    vi.stubGlobal("fetch", respond(undefined, { status: 204 }));
    await expect(getClientApi("/api/v1/health/ready")).resolves.toBeUndefined();
  });

  it("refuses a non-JSON success body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("<html>")),
    );
    await expect(getClientApi("/api/v1/health/ready")).rejects.toThrow(
      "non-JSON",
    );
  });
});

describe("time limits and failures (Feature 03 §3, A6, A7)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  it("gives up after 10 s with ApiTimeoutError", async () => {
    vi.stubGlobal("fetch", hang());
    const request = getClientApi("/api/v1/health/ready");
    const outcome = expect(request).rejects.toBeInstanceOf(ApiTimeoutError);
    await vi.advanceTimersByTimeAsync(CLIENT_TIMEOUT_MS - 1);
    await vi.advanceTimersByTimeAsync(1);
    await outcome;
  });

  it("does not time out a request that answers in time", async () => {
    vi.stubGlobal("fetch", respond({ status: "ready" }));
    await expect(getClientApi("/api/v1/health/ready")).resolves.toEqual({
      status: "ready",
    });
    // The timer was cleared: advancing past the limit changes nothing.
    await vi.advanceTimersByTimeAsync(CLIENT_TIMEOUT_MS * 2);
  });

  it("re-throws the caller's own abort unchanged, never as a failure", async () => {
    vi.stubGlobal("fetch", hang());
    const controller = new AbortController();
    const request = getClientApi("/api/v1/health/ready", {
      signal: controller.signal,
    });
    controller.abort();
    await expect(request).rejects.toMatchObject({ name: "AbortError" });
  });

  it("honours a signal that was aborted before the call", async () => {
    vi.stubGlobal("fetch", hang());
    const signal = AbortSignal.abort();
    await expect(
      getClientApi("/api/v1/health/ready", { signal }),
    ).rejects.toMatchObject({
      name: "AbortError",
    });
  });

  it("wraps a failed connection as ApiNetworkError", async () => {
    const cause = new TypeError("Failed to fetch");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Promise.reject(cause)),
    );
    await expect(getClientApi("/api/v1/health/ready")).rejects.toMatchObject({
      name: "ApiNetworkError",
      cause,
    } satisfies Partial<ApiNetworkError>);
  });

  it("has no time limit unless one is asked for", async () => {
    vi.stubGlobal("fetch", hang());
    let settled = false;
    void requestApi("/api/v1/health/ready").finally(() => {
      settled = true;
    });
    await vi.advanceTimersByTimeAsync(60_000);
    expect(settled).toBe(false);
  });
});

describe("mutateClientApi", () => {
  // No mutation endpoint exists in the contract yet, so the path is cast; the types are
  // tested against a fixture contract in types.test.ts.
  const path = "/api/v1/dev/form-probe" as never;

  it("sends a JSON body, the method and the Idempotency-Key", async () => {
    const fetchMock = respond({ ok: true }, { status: 201 });
    vi.stubGlobal("fetch", fetchMock);
    // Generated at runtime, never a literal: gitleaks reads `key: "<value>"` as a secret
    // (playbook §5), and a real form generates a UUID too.
    const idempotencyKey = crypto.randomUUID();
    await expect(
      mutateClientApi("post", path, { title: "Fiesta" } as never, {
        idempotencyKey,
      }),
    ).resolves.toEqual({ ok: true });

    const [, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    const headers = new Headers(init.headers);
    expect(init.method).toBe("POST");
    expect(init.body).toBe('{"title":"Fiesta"}');
    expect(headers.get("content-type")).toBe("application/json");
    expect(headers.get("idempotency-key")).toBe(idempotencyKey);
    expect(headers.get("accept")).toContain("application/problem+json");
  });

  it("sends no body or content type when there is none", async () => {
    const fetchMock = respond(undefined, { status: 204 });
    vi.stubGlobal("fetch", fetchMock);
    await mutateClientApi("delete", path, undefined as never);
    const [, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(init.method).toBe("DELETE");
    expect(init.body).toBeUndefined();
    expect(new Headers(init.headers).get("content-type")).toBeNull();
    expect(new Headers(init.headers).get("idempotency-key")).toBeNull();
  });

  it("applies the same time limit", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", hang());
    const outcome = expect(
      mutateClientApi("patch", path, {} as never),
    ).rejects.toBeInstanceOf(ApiTimeoutError);
    await vi.advanceTimersByTimeAsync(CLIENT_TIMEOUT_MS);
    await outcome;
  });
});

describe("the offline signal (Feature 03 slice 3.9)", () => {
  it("a failed connection raises it, and any response clears it", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))),
    );
    await expect(requestApi("/api/v1/health/ready")).rejects.toBeInstanceOf(
      ApiNetworkError,
    );
    expect(isNetworkFailing()).toBe(true);

    // A 500 is still a response: the network is fine, the server is not.
    vi.stubGlobal(
      "fetch",
      respond({ code: "internal_error" }, { status: 500 }),
    );
    await expect(requestApi("/api/v1/health/ready")).rejects.toBeInstanceOf(
      ApiError,
    );
    expect(isNetworkFailing()).toBe(false);
  });

  it("neither a timeout nor the caller's abort counts as offline", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", hang());
    const timedOut = expect(
      requestApi("/api/v1/health/ready", { timeoutMs: 100 }),
    ).rejects.toBeInstanceOf(ApiTimeoutError);
    await vi.advanceTimersByTimeAsync(100);
    await timedOut;

    const controller = new AbortController();
    const aborted = expect(
      requestApi("/api/v1/health/ready", { signal: controller.signal }),
    ).rejects.toMatchObject({
      name: "AbortError",
    });
    controller.abort();
    await aborted;
    expect(isNetworkFailing()).toBe(false);
  });
});
