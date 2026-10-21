import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Next's request headers and the server-only guard, outside a Next server.
const incoming = new Headers();
vi.mock("next/headers", () => ({ headers: async () => incoming }));
vi.mock("server-only", () => ({}));

const { forwardedHeaders, CONTEXT_HEADERS } = await import("./forwarding");
const { getPublicApi } = await import("./public");
const { getSessionApi } = await import("./session");

// The real API is exercised by e2e/api-clients.spec.ts; here only the outgoing request.
const fetchMock = vi.fn(
	async () =>
		new Response(JSON.stringify({ status: "ready" }), {
			headers: { "content-type": "application/json" },
		}),
);

function sentHeaders(): Headers {
	const init = fetchMock.mock.calls.at(-1)?.at(1) as RequestInit | undefined;
	return new Headers(init?.headers);
}

describe("server API clients (Feature 03 §6, A4)", () => {
	beforeEach(() => {
		vi.stubGlobal("fetch", fetchMock);
		for (const name of [...incoming.keys()]) incoming.delete(name);
		incoming.set("cookie", "session=abc");
		incoming.set("authorization", "Bearer abc");
		incoming.set("x-request-id", "req-1");
		incoming.set("traceparent", "00-trace-span-01");
		incoming.set("x-forwarded-for", "203.0.113.7");
	});

	afterEach(() => {
		vi.unstubAllGlobals();
	});

	it("the public client never forwards identity headers", async () => {
		await getPublicApi("/api/v1/health/ready");
		const sent = sentHeaders();
		expect(sent.get("cookie")).toBeNull();
		expect(sent.get("authorization")).toBeNull();
		expect(sent.get("x-request-id")).toBe("req-1");
		expect(sent.get("traceparent")).toBe("00-trace-span-01");
		expect(sent.get("x-forwarded-for")).toBe("203.0.113.7");
	});

	it("the public client drops identity headers a caller passes in", async () => {
		await getPublicApi("/api/v1/health/ready", { headers: { Cookie: "smuggled=1" } });
		expect(sentHeaders().get("cookie")).toBeNull();
	});

	it("the session client forwards the cookie and context", async () => {
		await getSessionApi("/api/v1/health/ready");
		const sent = sentHeaders();
		expect(sent.get("cookie")).toBe("session=abc");
		expect(sent.get("authorization")).toBe("Bearer abc");
		expect(sent.get("x-request-id")).toBe("req-1");
	});

	it("calls the internal API origin with a bounded timeout", async () => {
		await getPublicApi("/api/v1/health/ready");
		const [url, init] = fetchMock.mock.calls.at(-1) as unknown as [URL, RequestInit];
		expect(String(url)).toBe("http://127.0.0.1:8000/api/v1/health/ready");
		expect(init.signal).toBeInstanceOf(AbortSignal);
	});

	it("refuses a path outside /api/v1", async () => {
		await expect(getPublicApi("/admin" as "/api/v1/health/ready")).rejects.toThrow(/api\/v1/);
	});
});

describe("forwardedHeaders", () => {
	it("copies only the named headers that are present", () => {
		const source = new Headers({ "x-request-id": "r", other: "x" });
		const result = forwardedHeaders(source, CONTEXT_HEADERS);
		expect([...result.keys()]).toEqual(["x-request-id"]);
	});
});
