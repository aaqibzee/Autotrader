import { describe, expect, it } from "vitest";
import { buildContentSecurityPolicy, configuredOrigin } from "./csp";

function directives(policy: string): Record<string, string> {
  return Object.fromEntries(
    policy.split("; ").map((directive) => {
      const [name, ...values] = directive.split(" ");
      return [name, values.join(" ")];
    }),
  );
}

describe("buildContentSecurityPolicy", () => {
  it("produces exactly the production directive set", () => {
    // Asserting the whole policy means any widening shows up as a diff in review.
    expect(directives(buildContentSecurityPolicy({ nonce: "abc", development: false }))).toEqual({
      "default-src": "'self'",
      "script-src": "'self' 'nonce-abc' 'strict-dynamic'",
      "style-src": "'self' 'nonce-abc'",
      "style-src-elem": "'self' 'nonce-abc'",
      "style-src-attr": "'unsafe-inline'",
      "img-src": "'self' data: blob:",
      "connect-src": "'self'",
      "font-src": "'self'",
      "object-src": "'none'",
      "base-uri": "'self'",
      "form-action": "'self'",
      "frame-ancestors": "'none'",
    });
  });

  it("allows inline style attributes only, never inline style elements (A2)", () => {
    const policy = directives(buildContentSecurityPolicy({ nonce: "abc", development: false }));
    expect(policy["style-src-elem"]).not.toContain("unsafe-inline");
    expect(policy["style-src"]).not.toContain("unsafe-inline");
    expect(policy["script-src"]).not.toContain("unsafe-inline");
  });

  it("adds unsafe-eval to scripts in development only", () => {
    const dev = directives(buildContentSecurityPolicy({ nonce: "abc", development: true }));
    expect(dev["script-src"]).toBe("'self' 'nonce-abc' 'strict-dynamic' 'unsafe-eval'");
  });

  it("adds configured origins to their directives", () => {
    const policy = directives(
      buildContentSecurityPolicy({
        nonce: "abc",
        development: false,
        imageCdnOrigin: "https://img.example.test/path",
        errorIngestOrigin: "https://ingest.example.test",
        uploadsBucketOrigin: "https://uploads.example.test",
      }),
    );
    expect(policy["img-src"]).toBe("'self' data: blob: https://img.example.test");
    expect(policy["connect-src"]).toBe(
      "'self' https://ingest.example.test https://uploads.example.test",
    );
  });
});

describe("configuredOrigin", () => {
  it.each([
    ["https://img.example.test/a?b", "https://img.example.test"],
    ["http://127.0.0.1:9000", "http://127.0.0.1:9000"],
    ["http://localhost:9000", "http://localhost:9000"],
    ["http://img.example.test", undefined],
    ["not a url", undefined],
    ["", undefined],
    [undefined, undefined],
  ])("%s -> %s", (input, expected) => {
    expect(configuredOrigin(input)).toBe(expected);
  });
});
