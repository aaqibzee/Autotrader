import { test as base, expect, type Page } from "@playwright/test";

/**
 * Every e2e spec imports `test` and `expect` from here, never from `@playwright/test`
 * (oxlint `no-restricted-imports`). The extended `test` fails any test whose pages report
 * a Content Security Policy violation (Feature 03 slice 3.2), so a component that needs a
 * policy change is caught where it is introduced. Uses the fixture `page` only
 * (Feature 01 §14: manually created contexts leak).
 */
export type CspViolation = {
  directive: string;
  blockedUri: string;
  sample: string;
  documentUri: string;
};

/**
 * Records violations from `securitypolicyviolation` events on every document the page
 * loads. The listener is an init script and the sink an exposed binding, both injected
 * over the DevTools protocol, so the CSP under test cannot block the guard itself.
 */
export async function recordCspViolations(page: Page): Promise<CspViolation[]> {
  const violations: CspViolation[] = [];
  await page.exposeBinding(
    "__reportCspViolation",
    (_source, violation: CspViolation) => {
      violations.push(violation);
    },
  );
  await page.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (event) => {
      const report = (
        window as unknown as { __reportCspViolation: (v: unknown) => void }
      ).__reportCspViolation;
      void report({
        directive: event.effectiveDirective,
        blockedUri: event.blockedURI,
        sample: event.sample,
        documentUri: event.documentURI,
      });
    });
  });
  return violations;
}

type Fixtures = {
  /** Set `test.use({ allowCspViolations: true })` only in specs that assert on them. */
  allowCspViolations: boolean;
  cspViolations: CspViolation[];
};

export const test = base.extend<Fixtures>({
  allowCspViolations: [false, { option: true }],
  cspViolations: [
    async ({ page, allowCspViolations }, use) => {
      const violations = await recordCspViolations(page);
      await use(violations);
      if (!allowCspViolations) {
        expect(
          violations,
          "pages in this test reported CSP violations",
        ).toEqual([]);
      }
    },
    { auto: true },
  ],
});

export { expect };

/**
 * Waits until React has hydrated the page (components/providers.tsx sets the marker).
 * Use before typing or pressing keys: input before hydration goes to inert server markup.
 */
export async function gotoHydrated(page: Page, url: string): Promise<void> {
  await page.goto(url);
  await page.locator("html[data-hydrated]").waitFor({ state: "attached" });
}
