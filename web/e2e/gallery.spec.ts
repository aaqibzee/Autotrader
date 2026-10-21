import { expect, gotoHydrated, test } from "./fixtures";

// Feature 03 slice 3.6: the gallery renders every component on a production build with no
// CSP violation (the fixture fails the test on any). Screenshots and axe come in 3.14.
test("the component gallery renders every section", async ({ page }) => {
  await page.goto("/dev/components");
  await expect(
    page.getByRole("heading", { level: 1, name: "Component gallery" }),
  ).toBeVisible();
  for (const name of [
    "Buttons",
    "Text inputs",
    "Selects",
    "Pagination",
    "Breadcrumbs",
  ]) {
    await expect(
      page.getByRole("heading", { level: 2, name, exact: true }),
    ).toBeVisible();
  }
});

test("native controls work with no script of their own", async ({ page }) => {
  await page.goto("/dev/components#choices");
  const checkbox = page.getByRole("checkbox", {
    name: "Likely ULEZ compliant",
  });
  await checkbox.check();
  await expect(checkbox).toBeChecked();

  const toggle = page.getByRole("switch", { name: "Email me new matches" });
  await toggle.click();
  await expect(toggle).toBeChecked();

  await page.getByRole("radio", { name: "Manual" }).check();
  await expect(
    page.getByRole("radio", { name: "Automatic" }),
  ).not.toBeChecked();
});

test("controls meet the 24px target minimum at phone width", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/dev/components");
  const undersized = await page
    // Inline text links (`data-inline-link`) are exempt: SC 2.5.8's "inline" exception.
    // A slider's range input is visually hidden; its thumb is what a finger hits (3.8).
    .locator(
      "main :is(button, a:not([data-inline-link]), select, input:not([type=checkbox]):not([type=radio]):not([type=range]), label:has(input), [data-slider-thumb])",
    )
    .evaluateAll((elements) =>
      elements
        .map((element) => {
          const box = element.getBoundingClientRect();
          return {
            text:
              element.textContent?.trim() || element.getAttribute("aria-label"),
            box,
          };
        })
        .filter(
          ({ box }) => box.width > 0 && (box.width < 24 || box.height < 24),
        )
        .map(
          ({ text, box }) =>
            `${text} ${Math.round(box.width)}x${Math.round(box.height)}`,
        ),
    );
  expect(undersized).toEqual([]);
});

// Slice 3.7: React Aria overlays render style attributes; the CSP fixture proves the A2
// policy allows them while still refusing un-nonced <style>.
test("the filter sheet opens from the keyboard, without animation under reduced motion", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.setViewportSize({ width: 375, height: 800 });
  await gotoHydrated(page, "/dev/components#overlays");

  const trigger = page.getByRole("button", { name: "Filters", exact: true });
  await trigger.focus();
  await page.keyboard.press("Enter");

  const sheet = page.getByRole("dialog", { name: "Filters" });
  await expect(sheet).toBeVisible();
  // Fully in place immediately: no transform left from the slide-in animation.
  const offset = await sheet.evaluate((element) => {
    const modal = element.closest(".fixed") ?? element;
    return {
      transform: getComputedStyle(modal).transform,
      bottom: Math.round(
        window.innerHeight - modal.getBoundingClientRect().bottom,
      ),
    };
  });
  expect(offset.bottom).toBe(0);
  expect(["none", "matrix(1, 0, 0, 1, 0, 0)"]).toContain(offset.transform);
  await expect(sheet).toContainText("Fuel type");

  await page.keyboard.press("Escape");
  await expect(sheet).toBeHidden();
  await expect(trigger).toBeFocused();
});

test("toasts announce errors assertively and never stack duplicates", async ({
  page,
}) => {
  await gotoHydrated(page, "/dev/components#toasts");
  // Scoped to the toast region: Next's route announcer is also a role="alert".
  const toasts = page.getByRole("region", { name: "Notifications" });
  await page
    .getByRole("button", { name: "Ten identical errors (shows one)" })
    .click();
  await expect(toasts.getByRole("alert")).toHaveCount(1);
  await expect(toasts.getByRole("alert")).toHaveText(
    "We could not save your search.",
  );
  await page.getByRole("button", { name: "Success toast" }).click();
  await expect(
    toasts.getByRole("status").filter({ hasText: "Search saved." }),
  ).toBeVisible();
});

// Slice 3.8: Combobox and RangeSlider in a real browser, with the CSP fixture watching.
test("the make combobox filters without accents and selects from the keyboard", async ({
  page,
}) => {
  // No `#combobox` hash: Next scrolls to a hash target after hydration, and React Aria
  // closes an open popover when the page scrolls, so the list could vanish mid-test.
  await gotoHydrated(page, "/dev/components");
  const make = page.getByRole("combobox", { name: "Make", exact: true });
  await make.scrollIntoViewIfNeeded();
  await make.focus();
  await page.keyboard.type("citroen");
  const listbox = page.getByRole("listbox");
  await expect(listbox.getByRole("option")).toHaveText(["Citroën"]);
  await page.keyboard.press("ArrowDown");
  await expect(make).toHaveAttribute("aria-activedescendant", /.+/);
  await page.keyboard.press("Enter");
  await expect(make).toHaveValue("Citroën");
  await expect(listbox).toBeHidden();

  await make.fill("zzz");
  await expect(
    page.getByRole("status").filter({ hasText: "No matches" }),
  ).toBeVisible();
});

test("the price slider moves by keyboard and its thumbs never cross", async ({
  page,
}) => {
  await gotoHydrated(page, "/dev/components#range-slider");
  const price = page.getByRole("group", { name: "Price", exact: true });
  const low = price.getByRole("slider", { name: "Minimum Price" });
  const high = price.getByRole("slider", { name: "Maximum Price" });
  await expect(low).toHaveAttribute("aria-valuetext", "£5,000");

  // The thumb's position comes from a style attribute rendered on the server (A2).
  const thumb = price.locator("[data-slider-thumb]").first();
  const before = (await thumb.boundingBox())?.x ?? 0;
  await low.focus();
  await page.keyboard.press("PageUp");
  await expect(low).toHaveAttribute("aria-valuetext", "£10,000");
  await expect(price.locator("output")).toHaveText("£10,000 – £20,000");
  expect((await thumb.boundingBox())?.x ?? 0).toBeGreaterThan(before);

  await page.keyboard.press("End");
  await expect(low).toHaveAttribute("aria-valuetext", "£20,000");
  await page.keyboard.press("ArrowRight");
  await expect(low).toHaveAttribute("aria-valuetext", "£20,000");
  await expect(high).toHaveAttribute("aria-valuetext", "£20,000");
});

// Slice 3.9: states and the offline banner on a production build.
test("the offline banner follows the network and failed requests", async ({
  page,
  context,
}) => {
  await gotoHydrated(page, "/dev/components#offline");
  const banner = page.locator("[data-offline-banner]");
  await expect(banner).toBeEmpty();

  await context.setOffline(true);
  await expect(banner).toContainText("You appear to be offline");
  await context.setOffline(false);
  await expect(banner).toBeEmpty();

  // No response while the browser still believes it is online (dead Wi-Fi, API down).
  await page.getByRole("button", { name: "Simulate a failed request" }).click();
  await expect(banner).toContainText("You appear to be offline");
  await page
    .getByRole("button", { name: "Simulate a successful request" })
    .click();
  await expect(banner).toBeEmpty();
});

test("a rate limit counts down and enables retry at zero", async ({ page }) => {
  await page.clock.install();
  await gotoHydrated(page, "/dev/components#states");
  const notice = page.locator('[data-demo="rate-limited"]');
  const retry = notice.getByRole("button", { name: "Try again" });

  await expect(notice).toContainText("Try again in 0:15");
  await expect(retry).toBeDisabled();
  await expect(notice.getByRole("status")).toHaveText(
    "You can try again in 15 seconds.",
  );

  await page.clock.runFor(16_000);
  await expect(retry).toBeEnabled();
  await expect(notice.getByRole("status")).toHaveText("You can try again now.");
  await expect(notice).not.toContainText("Try again in");

  // Retrying into another 429 starts a fresh wait.
  await retry.click();
  await expect(retry).toBeDisabled();
  await expect(notice).toContainText("Try again in 0:15");
});

test("an unavailable integration offers to continue manually", async ({
  page,
}) => {
  await gotoHydrated(page, "/dev/components#states");
  const unavailable = page.locator('[data-problem-kind="unavailable"]');
  await expect(
    unavailable.getByRole("heading", { name: "Lookup unavailable" }),
  ).toBeVisible();
  await expect(
    unavailable.getByRole("button", { name: "Enter details manually" }),
  ).toBeVisible();
  // The request id is shown small, for support, next to the retry button.
  const serverError = page
    .locator('[data-problem-kind="retryable"]')
    .filter({ hasText: "req_01J9Z6Q4X8K2M3N5P7R9S1T3V5" });
  await expect(
    serverError.getByRole("button", { name: "Try again" }),
  ).toBeVisible();
});
