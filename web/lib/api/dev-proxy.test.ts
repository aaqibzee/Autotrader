import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
const { devApiProxyEnabled, proxyToApi } = await import("./dev-proxy");

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("dev API proxy (e2e and local only)", () => {
  it("is off unless DEV_API_PROXY=1, and then answers 404 without calling out", async () => {
    expect(devApiProxyEnabled({})).toBe(false);
    expect(devApiProxyEnabled({ DEV_API_PROXY: "1" })).toBe(true);
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    vi.stubEnv("DEV_API_PROXY", "");
    const response = await proxyToApi(
      new Request("http://web.test/api/v1/health/ready"),
    );
    expect(response.status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("forwards only the API client's headers and passes the answer back", async () => {
    vi.stubEnv("DEV_API_PROXY", "1");
    vi.stubEnv("API_INTERNAL_URL", "http://api.test");
    const fetchMock = vi.fn(
      async () =>
        new Response('{"code":"rate_limited"}', {
          status: 429,
          headers: {
            "content-type": "application/problem+json",
            "retry-after": "3",
            "x-internal": "never-forwarded",
          },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const key = crypto.randomUUID();

    const response = await proxyToApi(
      new Request("http://web.test/api/v1/dev/form-probe/probe-1?x=1", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "idempotency-key": key,
          authorization: "Bearer not-forwarded",
        },
        body: '{"name":"Ford"}',
      }),
    );

    const [url, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toBe("http://api.test/api/v1/dev/form-probe/probe-1?x=1");
    expect(init.method).toBe("POST");
    const sent = new Headers(init.headers);
    expect(sent.get("idempotency-key")).toBe(key);
    expect(sent.get("authorization")).toBeNull();
    expect(new TextDecoder().decode(init.body as ArrayBuffer)).toBe(
      '{"name":"Ford"}',
    );

    expect(response.status).toBe(429);
    expect(response.headers.get("retry-after")).toBe("3");
    expect(response.headers.get("x-internal")).toBeNull();
    expect(await response.text()).toBe('{"code":"rate_limited"}');
  });

  it("sends no body for a GET", async () => {
    vi.stubEnv("DEV_API_PROXY", "1");
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    await proxyToApi(new Request("http://web.test/api/v1/health/ready"));
    const [url, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toBe("http://127.0.0.1:8000/api/v1/health/ready");
    expect(init.body).toBeUndefined();
  });
});
