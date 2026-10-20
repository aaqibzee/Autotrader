import { expect, test } from "./fixtures";

test.describe("Content Security Policy (Feature 03 slice 3.2)", () => {
  test("pages are served by a production build with the split style policy", async ({ page }) => {
    const response = await page.goto("/");
    const policy = response?.headers()["content-security-policy"] ?? "";

    // `next dev` adds 'unsafe-eval'; its absence proves e2e runs a production server (A3).
    expect(policy).not.toContain("unsafe-eval");
    expect(policy).toMatch(/style-src-elem 'self' 'nonce-[^']+'/);
    expect(policy).toContain("style-src-attr 'unsafe-inline'");
  });

  test.describe("the guard", () => {
    test.use({ allowCspViolations: true });

    test("catches an un-nonced style element and allows style attributes", async ({
      page,
      cspViolations,
    }) => {
      await page.goto("/dev/csp-probe");
      await expect(page.getByRole("heading", { name: "CSP probe" })).toBeVisible();

      // The policy did its job in the browser, not only in the header.
      await expect(page.getByTestId("blocked-element")).not.toHaveCSS(
        "text-decoration-line",
        "underline",
      );
      await expect(page.getByTestId("allowed-attribute")).toHaveCSS("font-weight", "700");

      // ...and the guard saw it: one blocked element, no attribute reports.
      await expect.poll(() => cspViolations.map((v) => v.directive)).toEqual(["style-src-elem"]);
    });
  });
});
