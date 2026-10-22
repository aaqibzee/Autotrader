import { expect, gotoHydrated, test } from "./fixtures";

// Feature 03 slice 3.11: the layouts on a production build.

test("the account island fills in late without shifting the layout (CLS < 0.01)", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const record = window as unknown as { __cls: number };
    record.__cls = 0;
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries() as Array<
        PerformanceEntry & { value: number; hadRecentInput: boolean }
      >) {
        if (!entry.hadRecentInput) record.__cls += entry.value;
      }
    }).observe({ type: "layout-shift", buffered: true });
  });
  await page.goto("/dev/shell?delay=1500");
  const island = page.locator("[data-account-island]");
  await expect(island).toHaveAttribute("data-account-island", "loading");
  const before = await island.boundingBox();

  await expect(island).toHaveAttribute("data-account-island", "signed-in", {
    timeout: 10_000,
  });
  await expect(
    page.getByRole("link", { name: /signed in as Sam Patel/ }),
  ).toBeVisible();
  const after = await island.boundingBox();
  expect(after).toEqual(before);

  // Let any late shift be recorded before reading the total.
  await page.waitForTimeout(500);
  const cls = await page.evaluate(
    () => (window as unknown as { __cls: number }).__cls,
  );
  expect(cls).toBeLessThan(0.01);
});

for (const path of ["/", "/dealer", "/dev/components", "/dev/shell"]) {
  test(`no sideways scroll at 320 px: ${path}`, async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 700 });
    await page.goto(path);
    const widths = await page.evaluate(() => ({
      scroll: document.documentElement.scrollWidth,
      client: document.documentElement.clientWidth,
    }));
    expect(widths.scroll).toBeLessThanOrEqual(320);
    expect(widths.scroll).toBeLessThanOrEqual(widths.client);
  });
}

test("dealer nav: a bottom bar below lg, a side nav from lg", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/dealer");
  const bottom = page.locator('[data-dealer-nav="bottom"]');
  const side = page.locator('[data-dealer-nav="side"]');
  await expect(bottom).toBeVisible();
  await expect(side).toBeHidden();
  await expect(bottom.getByRole("link")).toHaveText([
    "Stock",
    "Leads",
    "Team",
    "Settings",
  ]);

  await page.setViewportSize({ width: 1280, height: 800 });
  await expect(side).toBeVisible();
  await expect(bottom).toBeHidden();
});

test("the skip link is the first stop and moves focus to the content", async ({
  page,
}) => {
  await gotoHydrated(page, "/dev/shell");
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to content" });
  await expect(skip).toBeFocused();
  await expect(skip).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(page.locator("main#main")).toBeFocused();
});
