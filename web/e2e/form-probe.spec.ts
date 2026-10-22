import { randomUUID } from "node:crypto";
import type { Page } from "@playwright/test";
import { expect, gotoHydrated, test } from "./fixtures";

// Feature 03 slice 3.10: useApiForm against the real API and middleware, through the
// dev-only form probe (backend endpoints/dev.py). Each test gets its own probe record.
const API = "http://127.0.0.1:8000";

async function openProbe(page: Page) {
  const id = `probe-${randomUUID().slice(0, 12)}`;
  await gotoHydrated(page, `/dev/components?probe=${id}`);
  const form = page.locator(`[data-probe-id="${id}"]`);
  await form.scrollIntoViewIfNeeded();
  await expect(form.getByRole("button", { name: "Save" })).toBeVisible();
  const executions = async () =>
    (await (
      await page.request.get(`${API}/api/v1/dev/form-probe/${id}/executions`)
    ).json()) as Record<string, number>;
  return { id, form, executions, path: `/api/v1/dev/form-probe/${id}` };
}

const saved = (page: Page) =>
  page.getByRole("status").filter({ hasText: /^Saved/ });

test("a double-click sends one request", async ({ page }) => {
  const { form, executions, path } = await openProbe(page);
  let posts = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && new URL(request.url()).pathname === path)
      posts += 1;
  });
  await form.getByRole("button", { name: "Save" }).dblclick();
  await expect(saved(page)).toBeVisible();
  expect(posts).toBe(1);
  expect(Object.values(await executions())).toEqual([1]);
});

test("a request lost on the way back is retried with the same key and runs once", async ({
  page,
}) => {
  const { form, executions, path } = await openProbe(page);
  const keys: string[] = [];
  let first = true;
  await page.route(`**${path}`, async (route) => {
    const request = route.request();
    if (request.method() !== "POST") return route.continue();
    keys.push((await request.headerValue("idempotency-key")) ?? "");
    if (first) {
      first = false;
      // The API runs the save, but the answer never reaches the browser.
      await route.fetch();
      return route.abort("connectionreset");
    }
    return route.continue();
  });

  await form.getByRole("textbox", { name: "Name" }).fill("Ford Focus");
  await form.getByRole("button", { name: "Save" }).click();
  await expect(
    form.getByRole("heading", { name: "You appear to be offline" }),
  ).toBeVisible();
  await form.getByRole("button", { name: "Try again" }).click();
  await expect(saved(page)).toHaveText("Saved “Ford Focus”.");

  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
  // The retry was a replay: the save itself ran once.
  expect(await executions()).toEqual({ [keys[0] ?? ""]: 1 });
});

test("422 messages land on their fields; an unknown field is shown for the form", async ({
  page,
}) => {
  const { form } = await openProbe(page);
  const name = form.getByRole("textbox", { name: "Name" });
  await name.fill("Taken");
  await form.getByRole("button", { name: "Save" }).click();
  await expect(name).toHaveAttribute("aria-invalid", "true");
  await expect(name).toHaveAccessibleDescription(
    /That name is already in use\./,
  );
  await expect(form.getByRole("alert")).toHaveText(
    "Choose a dealership before saving.",
  );
  await expect(name).toHaveValue("Taken");
});

test("409 opens the conflict dialog and 'Re-apply mine' saves", async ({
  page,
}) => {
  const { id, form } = await openProbe(page);
  await page.request.post(`${API}/api/v1/dev/form-probe/${id}/touch`);
  await form.getByRole("textbox", { name: "Name" }).fill("My edit");
  await form.getByRole("button", { name: "Save" }).click();

  const dialog = page.getByRole("dialog", {
    name: "This was changed by someone else",
  });
  await expect(dialog).toBeVisible();
  const nameRow = dialog.getByRole("row", { name: /Name/ });
  await expect(nameRow).toContainText("My edit");
  await expect(nameRow).toContainText("Ford Fiesta (edited)");

  await dialog.getByRole("button", { name: "Re-apply mine" }).click();
  await expect(dialog).toBeHidden();
  await expect(saved(page)).toHaveText("Saved “My edit”.");
});

test("429 shows the countdown, then retry works", async ({ page }) => {
  const { form } = await openProbe(page);
  await form.getByLabel("What the API should do").selectOption("rate_limited");
  await form.getByRole("button", { name: "Save" }).click();
  const notice = form.locator('[data-problem-kind="rate-limited"]');
  await expect(notice).toContainText("Try again in 0:0");
  const retry = notice.getByRole("button", { name: "Try again" });
  await expect(retry).toBeDisabled();
  await expect(retry).toBeEnabled({ timeout: 6_000 });
  await expect(notice.getByRole("status")).toHaveText("You can try again now.");
});

test("503 integration_unavailable offers to continue manually", async ({
  page,
}) => {
  const { form } = await openProbe(page);
  await form.getByLabel("What the API should do").selectOption("unavailable");
  await form.getByRole("button", { name: "Save" }).click();
  const state = form.locator('[data-problem-kind="unavailable"]');
  await expect(
    state.getByRole("heading", { name: "Lookup unavailable" }),
  ).toBeVisible();
  await state.getByRole("button", { name: "Enter details manually" }).click();
  await expect(form.getByLabel("What the API should do")).toHaveValue("ok");
});

test("a request that hangs shows the error state with retry after 10 s", async ({
  page,
}) => {
  test.setTimeout(45_000);
  const { form } = await openProbe(page);
  await form.getByLabel("What the API should do").selectOption("hang");
  const started = Date.now();
  await form.getByRole("button", { name: "Save" }).click();
  const state = form.locator('[data-problem-kind="timeout"]');
  await expect(
    state.getByRole("heading", { name: "This is taking too long" }),
  ).toBeVisible({
    timeout: 15_000,
  });
  expect(Date.now() - started).toBeGreaterThanOrEqual(9_500);
  await expect(state.getByRole("button", { name: "Try again" })).toBeEnabled();
});
