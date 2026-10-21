import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    include: [
      "lib/**/*.test.{ts,tsx}",
      "app/**/*.test.{ts,tsx}",
      "components/**/*.test.{ts,tsx}",
      "styles/**/*.test.ts",
    ],
    clearMocks: true,
    restoreMocks: true,
    coverage: {
      provider: "v8",
      // Components and hooks are measured too (Feature 03 A14), not only lib/*.ts.
      include: ["lib/**/*.{ts,tsx}", "components/**/*.{ts,tsx}", "styles/**/*.ts"],
      exclude: ["**/*.test.{ts,tsx}", "lib/api/schema.d.ts"],
      thresholds: {
        // Feature 01 §14: every component formats through these helpers, so they are
        // fully covered; other modules are reported but not gated.
        "lib/format/**": { lines: 100, functions: 100, branches: 100, statements: 100 },
        // Feature 03 §1: the contrast maths decides what ships, so it is fully covered.
        "styles/contrast.ts": { lines: 100, functions: 100, branches: 100, statements: 100 },
        // Feature 03 A1: losing an early error, or reporting it twice, is silent in production.
        "lib/observability/lazy-sentry.ts": { lines: 100, functions: 100, branches: 100, statements: 100 },
        // Feature 03 §3, §6: an open redirect or a forwarded cookie is a security bug.
        "lib/navigation/safe-next.ts": { lines: 100, functions: 100, branches: 100, statements: 100 },
        "lib/api/forwarding.ts": { lines: 100, functions: 100, branches: 100, statements: 100 },
      },
    },
  },
});
