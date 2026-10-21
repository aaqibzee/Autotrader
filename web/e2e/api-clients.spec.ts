import { randomUUID } from "node:crypto";
import { expect, test } from "./fixtures";

// Feature 03 §6, slice 3.4: public HTML is identical for every visitor, and signed-in
// surfaces are never cached or indexed.

test("the public API client never sends the session cookie to the API", async ({
  page,
}) => {
  await page
    .context()
    .addCookies([
      { name: "session", value: randomUUID(), url: "http://127.0.0.1:3000" },
    ]);
  await page.goto("/dev/api-clients");

  // What the real API received (backend dev echo route: names only, never values).
  await expect(page.getByTestId("public-cookie")).toHaveText("absent");
  await expect(page.getByTestId("public-x-request-id")).toHaveText("received");
  // Same request, session client: proves the cookie was there to forward.
  await expect(page.getByTestId("session-cookie")).toHaveText("received");
});

test("a public page is identical with and without a session cookie", async ({
  request,
}) => {
  async function render(cookie?: string) {
    const response = await request.get("/", {
      headers: cookie ? { cookie } : {},
    });
    expect(response.status()).toBe(200);
    const headers = response.headers();
    const nonce = /'nonce-([^']+)'/.exec(
      headers["content-security-policy"] ?? "",
    )?.[1];
    expect(nonce, "CSP nonce").toBeTruthy();
    return normalise(await response.text(), nonce!, headers["x-request-id"]);
  }

  const anonymous = await render();
  const signedIn = await render(`session=${randomUUID()}`);
  expect(signedIn).toBe(anonymous);
});

/**
 * Per-request values that are not personal: the CSP nonce, this response's own request id
 * (error states print it for support), and Sentry's trace meta tags (`clientTraceMetadata`,
 * present only when a DSN is configured). Each is replaced by its exact value, never by a
 * pattern such as "any UUID", which would also hide a leaked user id. Anything else that
 * differs between the two renders is a leak.
 */
function normalise(
  html: string,
  nonce: string,
  requestId: string | undefined,
): string {
  const withoutRequestId = requestId
    ? html.replaceAll(requestId, "REQUEST_ID")
    : html;
  return withoutRequestId
    .replaceAll(nonce, "NONCE")
    .replace(/<meta name="(?:sentry-trace|baggage)" content="[^"]*"\/?>/g, "");
}

for (const path of [
  "/dealer",
  "/account",
  "/admin",
  "/dealer/anything-below",
]) {
  test(`${path} is private and not indexed`, async ({ request }) => {
    const response = await request.get(path);
    const headers = response.headers();
    expect(headers["cache-control"]).toContain("private");
    expect(headers["cache-control"]).toContain("no-store");
    expect(headers["x-robots-tag"]).toBe("noindex");
  });
}

test("public pages are not marked noindex", async ({ request }) => {
  const response = await request.get("/");
  expect(response.headers()["x-robots-tag"]).toBeUndefined();
});
