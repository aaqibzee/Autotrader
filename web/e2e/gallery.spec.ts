import { expect, test } from "./fixtures";

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
    .locator(
      "main :is(button, a:not([data-inline-link]), select, input:not([type=checkbox]):not([type=radio]), label:has(input))",
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
  await page.goto("/dev/components#overlays");

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
  await page.goto("/dev/components#toasts");
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
