import { expect, test } from "./fixtures";

test("SSR home page reports API readiness", async ({ page }) => {
	await page.goto("/");
	await expect(page.getByRole("heading", { name: "The road starts here." })).toBeVisible();
	await expect(page.getByRole("heading", { name: "Service readiness" })).toBeVisible();
	await expect(page.getByText("ready", { exact: true })).toBeVisible();
});