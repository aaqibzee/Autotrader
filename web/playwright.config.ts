import { defineConfig, devices } from "@playwright/test";

const ci = Boolean(process.env.CI);

// e2e runs the production standalone server, exactly as systemd runs it on the VM, never
// `next dev`: dev mode changes the CSP, caching headers and chunks, so no header, CSP or
// bundle criterion could be proven against it (Feature 03 A3). CI builds in its own step
// and sets E2E_SKIP_BUILD; locally the first run builds.
const startWeb = "npm run start:standalone";
const webCommand = process.env.E2E_SKIP_BUILD
  ? startWeb
  : `npm run build:standalone && ${startWeb}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: ci,
  retries: ci ? 1 : 0,
  reporter: ci ? "github" : "list",
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command:
        "uv run --directory ../backend uvicorn app.main:app --host 127.0.0.1 --port 8000",
      url: "http://127.0.0.1:8000/health/live",
      reuseExistingServer: !ci,
      timeout: 120_000,
      env: { API_INTERNAL_URL: "http://127.0.0.1:8000" },
    },
    {
      command: webCommand,
      url: "http://127.0.0.1:3000",
      // Locally an already-running server is reused: if that is `next dev`, the CSP
      // spec's production check fails, which is the intended signal.
      reuseExistingServer: !ci,
      timeout: process.env.E2E_SKIP_BUILD ? 60_000 : 300_000,
      env: {
        API_INTERNAL_URL: "http://127.0.0.1:8000",
        HOSTNAME: "127.0.0.1",
        PORT: "3000",
        NODE_ENV: "production",
        NEXT_TELEMETRY_DISABLED: "1",
        // Dev-only routes (/dev/*) are on for e2e only (A3).
        ENABLE_COMPONENT_GALLERY: "1",
      },
    },
  ],
});
