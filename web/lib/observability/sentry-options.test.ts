import type { ErrorEvent } from "@sentry/nextjs";
import { describe, expect, it } from "vitest";
import { scrubEvent, sentryOptions } from "./sentry-options";

describe("Sentry scrubbing", () => {
  it("removes cookies, bodies, query strings, user and all headers but the request id", () => {
    const event = scrubEvent({
      type: undefined,
      user: { email: "jane@example.com" },
      request: {
        url: "https://example.test/search?postcode=SW1A1AA",
        cookies: { session: "secret" },
        data: { message: "call me on 07700 900123" },
        query_string: "postcode=SW1A1AA",
        headers: { cookie: "session=secret", "x-request-id": "req-1" },
      },
    } as ErrorEvent);

    expect(event.user).toBeUndefined();
    expect(event.request).toEqual({
      url: "https://example.test/search",
      headers: { "x-request-id": "req-1" },
    });
  });

  it("is disabled without a DSN", () => {
    expect(sentryOptions(undefined).enabled).toBe(false);
    expect(sentryOptions("https://key@o0.ingest.sentry.io/1").enabled).toBe(
      true,
    );
  });
});
