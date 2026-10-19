import { defineConfig, devices } from "@playwright/test";

const ci = Boolean(process.env.CI);

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
			command: "npm run dev -- --hostname 127.0.0.1",
			url: "http://127.0.0.1:3000",
			reuseExistingServer: !ci,
			timeout: 120_000,
		},
	],
});