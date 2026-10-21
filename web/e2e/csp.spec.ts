import { expect, test } from "./fixtures";

test.describe("Content Security Policy (Feature 03 slice 3.2)", () => {
  test("pages are served by a production build with the split style policy", async ({
    page,
  }) => {
    const response = await page.goto("/");
    const policy = response?.headers()["content-security-policy"] ?? "";

    // `next dev` adds 'unsafe-eval'; its absence proves e2e runs a production server (A3).
    expect(policy).not.toContain("unsafe-eval");
    expect(policy).toMatch(/style-src-elem 'self' 'nonce-[^']+'/);
    expect(policy).toContain("style-src-attr 'unsafe-inline'");
  });

  test("React Aria's runtime style gets the page nonce, which the DOM never shows", async ({
    page,
  }) => {
    await page.goto("/dev/components#overlays");
    // A React Aria pressable mounts usePress, which inserts its touch-action <style>.
    await expect(
      page.getByRole("button", { name: "Open modal" }),
    ).toBeVisible();

    // The style goes in from an effect after hydration, so wait for it.
    await expect(page.locator("style#react-aria-pressable-style")).toHaveCount(
      1,
    );
    const nonces = await page.evaluate(() => {
      const meta = document.querySelector<HTMLMetaElement>(
        'meta[name="csp-nonce"]',
      );
      const style = document.querySelector<HTMLStyleElement>(
        "style#react-aria-pressable-style",
      );
      return {
        meta: meta?.nonce ?? "",
        metaAttribute: meta?.getAttribute("nonce"),
        metaContent: meta?.getAttribute("content"),
        style: style?.nonce ?? "",
      };
    });
    expect(nonces.meta).not.toBe("");
    expect(nonces.style).toBe(nonces.meta);
    // Browsers blank a parsed nonce attribute, so script injected later cannot read it.
    expect(nonces.metaAttribute).toBe("");
    expect(nonces.metaContent).toBeNull();
    // The auto fixture fails this test if the style was blocked.
  });

  test.describe("the guard", () => {
    test.use({ allowCspViolations: true });

    test("catches an un-nonced style element and allows style attributes", async ({
      page,
      cspViolations,
    }) => {
      await page.goto("/dev/csp-probe");
      await expect(
        page.getByRole("heading", { name: "CSP probe" }),
      ).toBeVisible();

      // The policy did its job in the browser, not only in the header.
      await expect(page.getByTestId("blocked-element")).not.toHaveCSS(
        "text-decoration-line",
        "underline",
      );
      await expect(page.getByTestId("allowed-attribute")).toHaveCSS(
        "font-weight",
        "700",
      );

      // ...and the guard saw it: one blocked element, no attribute reports.
      await expect
        .poll(() => cspViolations.map((v) => v.directive))
        .toEqual(["style-src-elem"]);
    });
  });
});
