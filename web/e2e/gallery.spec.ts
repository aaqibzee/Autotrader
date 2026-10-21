import { expect, test } from "./fixtures";

// Feature 03 slice 3.6: the gallery renders every component on a production build with no
// CSP violation (the fixture fails the test on any). Screenshots and axe come in 3.14.
test("the component gallery renders every section", async ({ page }) => {
  await page.goto("/dev/components");
  await expect(page.getByRole("heading", { level: 1, name: "Component gallery" })).toBeVisible();
  for (const name of ["Buttons", "Text inputs", "Selects", "Pagination", "Breadcrumbs"]) {
    await expect(page.getByRole("heading", { level: 2, name, exact: true })).toBeVisible();
  }
});

test("native controls work with no script of their own", async ({ page }) => {
  await page.goto("/dev/components#choices");
  const checkbox = page.getByRole("checkbox", { name: "Likely ULEZ compliant" });
  await checkbox.check();
  await expect(checkbox).toBeChecked();

  const toggle = page.getByRole("switch", { name: "Email me new matches" });
  await toggle.click();
  await expect(toggle).toBeChecked();

  await page.getByRole("radio", { name: "Manual" }).check();
  await expect(page.getByRole("radio", { name: "Automatic" })).not.toBeChecked();
});

test("controls meet the 24px target minimum at phone width", async ({ page }) => {
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
          return { text: element.textContent?.trim() || element.getAttribute("aria-label"), box };
        })
        .filter(({ box }) => box.width > 0 && (box.width < 24 || box.height < 24))
        .map(({ text, box }) => `${text} ${Math.round(box.width)}x${Math.round(box.height)}`),
    );
  expect(undersized).toEqual([]);
});
