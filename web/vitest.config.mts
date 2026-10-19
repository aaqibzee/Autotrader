import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    include: ["lib/**/*.test.{ts,tsx}", "app/**/*.test.{ts,tsx}"],
    clearMocks: true,
    restoreMocks: true,
    coverage: {
      provider: "v8",
      include: ["lib/**/*.ts"],
      exclude: ["lib/**/*.test.ts", "lib/api/schema.d.ts"],
      thresholds: {
        // Feature 01 §14: every component formats through these helpers, so they are
        // fully covered; other modules are reported but not gated.
        "lib/format/**": { lines: 100, functions: 100, branches: 100, statements: 100 },
      },
    },
  },
});
