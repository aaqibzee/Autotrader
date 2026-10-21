# Feature 03 — Design System & App Shell

**Status:** Planning. Delivered in 14 slices: [03-design-system-and-app-shell.slices.md](03-design-system-and-app-shell.slices.md), which also lists the design amendments (A1–A16) applied below.
**Priority:** Must-Have
**Milestone:** M1 Foundation
**Effort:** 6h optimistic / 13h realistic / 20h pessimistic (slice plan: ~25 h, including the guards found missing while planning: A1–A3, A12)
*(raised from 5/10/16h after a scale review: the public-HTML caching rule, the shared
API-error/form plumbing, branded error pages and automated a11y/visual checks are
built once here instead of per feature. See "Scale review" at the end.)*
**Depends on:** 01

## Description

The visual language and page chrome for both surfaces: the **public consumer site**
and the **dealer portal**. Report §4 notes "this site has a high design bar; getting
'looks legit' takes real iteration even with AI." Building the components once,
before any feature page, stops every later feature from inventing its own buttons,
spacing, error handling and loading behaviour. Report §5 says car-shopping traffic
"skews heavily mobile," so everything is designed at 375px first.

---

## Scope

### 1. Tokens (Tailwind theme + CSS variables)
- Colour: neutral ink/surface scale, one brand accent, semantic success/warning/danger/info, and price-indicator colours (great/good/fair/high/no-rating, reused in Feature 12). Every pairing used for text meets WCAG 2.2 AA (4.5:1 body, 3:1 large text and UI boundaries), checked by a token contrast test.
- Type scale using a self-hosted font via `next/font` (Feature 01 §13), with `font-variant-numeric: tabular-nums` for prices and mileage
- Spacing, radius, shadow and z-index scales (z-index named: `header`, `sheet`, `modal`, `toast`), so overlays never fight
- Breakpoints: Tailwind defaults (`sm` 640, `md` 768, `lg` 1024, `xl` 1280). The filter sheet becomes a sidebar at `lg`.
- Light theme only for the MVP
- Tailwind's default palette is removed, so only contrast-checked tokens exist as colour utilities. Tokens are hex (A15).
- The product name and wordmark come from one `BRAND` constant (open decision 6 in the slices file)

### 2. Components (`web/components/ui/`)
- Button, IconButton, Input, Select, Combobox (searchable, for make/model), RangeSlider (price, mileage), Checkbox, RadioGroup, Toggle
- Card, Badge (incl. "Example listing", "Reserved", "Sold"), Tag
- Modal/Sheet (bottom sheet on mobile, used for filters), Tabs, Accordion
- Toast (one global provider, no ad-hoc inline success text)
- Skeleton loaders for listing cards and the detail page
- EmptyState and ErrorState (§4), Pagination, Breadcrumbs
- `ListingCard`: the most-reused composite (image, title, variant, price, year · mileage · fuel · transmission, location/distance, save heart, optional price-indicator slot). The heart is a client island (§6).
- **Interactive primitives are built on React Aria Components** (combobox, slider, dialog/sheet, tabs, toast region), styled with Tailwind. Hand-rolled comboboxes and sliders are the most common source of keyboard and screen-reader bugs. Bundle cost is checked by the §7 budget; if it fails, the fallback is importing per-component entry points. The range slider uses React Aria's slider *hooks* rather than its component, so values in pence are announced through `lib/format` (A17).

### 3. API errors, forms and request states (shared plumbing)
Every later form (dealer sign-up, listing edit, contact dealer, saved search, value my
car) uses these, so error handling is identical everywhere:
- **`ProblemCode` is an OpenAPI enum** and `problem-ui.ts` is a `Record<ProblemCode, …>`, so a new backend code fails the web typecheck until it has UI. `rate_limited` and `integration_unavailable` are added to the backend enum here. `ApiError` keeps `Retry-After` and extension members such as `current` (A5, A6). The typed client gains mutation methods (A7).
- **`useApiForm(schema, submit)`**: client-side validation (zod, mirroring the generated OpenAPI types, Feature 01 §5), a submit lock against double-submission, and mapping of a 422 Problem's `errors[]` onto fields by `field`. Unknown fields become a form-level error. Sends an `Idempotency-Key` (UUID generated when the form opens) for the endpoints Feature 01 §5 lists.
- **Problem `code` → UI** (one table, `web/lib/api/problem-ui.ts`):

  | Problem | UI |
  |---|---|
  | 409 `stale_update` | `ConflictDialog`: shows what changed, offers "Reload theirs" or "Re-apply mine" (re-submits with the new `updated_at`) |
  | 429 `rate_limited` | Inline message with the `Retry-After` countdown, never a toast storm |
  | 503 `integration_unavailable` | The feature's "unavailable — continue manually" variant of `ErrorState` |
  | 503 `dependency_unavailable` | Generic `ErrorState` with retry |
  | 401 | Redirect to sign-in with a same-origin `next` path (only relative paths accepted; no open redirect). The rule is `safeNextPath()` here; the sign-in page is Feature 04 (A10) |
  | 403 / 404 | `PermissionDenied` / `NotFound` states |
  | 5xx / network | `ErrorState` with retry and the `request_id` shown small, for support |
- **Client request timeout 10 s** (AbortController; SSR keeps 3 s). Timeouts and network failures are their own error classes (A6). After that the UI shows the error state with retry. **No spinner ever runs without a bound.**
- **Offline:** a banner driven by `navigator.onLine` plus fetch failures. Forms keep their entered values when a submit fails.

### 4. States and branded error pages
- `EmptyState` (illustration + message + primary action), `ErrorState` (variants: generic, unavailable, offline), `PermissionDenied`, `NotFound`
- **Branded `not-found.tsx` (404), a `Gone` page (410, with a slot for similar cars used by Features 08/13), `error.tsx` (500, with retry and `request_id`) and `global-error.tsx`.** *(Moved here from Feature 15, which now audits them.)*
- The static maintenance page served by the proxy (Feature 01 §16) is generated from the same styles by `web/scripts/build-maintenance.tsx` into `ops/nginx/maintenance.html` (what nginx serves while Next is down, so not `web/public/`), committed and freshness-checked in CI. System font stack, no external requests (A11).
- The 410 status needs a mechanism: the App Router has no `gone()`. 3.13 spikes a middleware rewrite with `status: 410`; Feature 08 adopts the result (A9).
- **Error responses are never cacheable:** 404/410/5xx pages send `Cache-Control: no-store` (410 may send `public, max-age=3600` because it's deliberate and stable). A transient 500 must never be stored by Cloudflare and served for 60 s. Feature 13's public cache header must therefore be set where the status is known, never as a blanket middleware or `next.config` header (A16).

### 5. Layouts
- Data the shell cannot have yet (account, valuation flag, footer make links, dealer status, saved ids) arrives as props or slots wired by Features 04, 09, 12 and 13. `ListingCard` takes a `ListingCardData` view model, not an API type (A8).
- `PublicLayout`: header (logo, search entry, "Value my car" — hidden while Feature 12's flag is off — sign in/account, "For dealers" link), footer (legal links, sitemap links by make). Skip-to-content link.
- `DealerLayout`: side nav on desktop, bottom nav on mobile (Stock, Leads, Team, Settings), dealer name and approval-status banner ("Awaiting approval: you can create drafts but not publish")
- `AdminLayout`: minimal, for Feature 14

### 6. Caching and personalisation rule (public pages)
Public pages are edge-cached (`s-maxage=60, stale-while-revalidate=300`, Features 08
and 13). Any personal data in that HTML would be served to the next visitor. So:
- **Public-route HTML is identical for every visitor.** Server components on public routes call the API through `getPublicApi`, which **never forwards the session cookie** (Feature 01 §3 forwarding is for authenticated routes only; the cookie-forwarding client is renamed `getSessionApi`). A CI check fails if any file under `web/app/(public)/` reaches the session client, directly or through any chain of imports (A4).
- User-specific bits are **client islands**: the header account slot (from `GET /users/me`), save hearts (Feature 09's id set), "Price dropped since you saved". Each island reserves its space so it causes no layout shift.
- Authenticated layouts (`/dealer`, `/account`, `/admin`) respond with `Cache-Control: private, no-store` and `X-Robots-Tag: noindex`.

### 7. Rendering and bundle budget
- Server components by default; `'use client'` only on interactive leaves (forms, sheet, gallery, islands)
- **No runtime CSS-in-JS.** Tailwind only, so stylesheets and `<style>` elements work under Feature 01 §11's nonce-based CSP without `unsafe-inline`. Style *attributes* (which nonces cannot cover, and React Aria server-renders) are allowed via `style-src-attr 'unsafe-inline'`; `script-src` is unchanged (A2).
- **First-load JS budget for the public shell: 133 kB gzipped** = the measured framework floor of 103 kB (Next runtime 46.8, `react-dom` 54.2, other 2.3; Next 15.5.28 / React 19.1.0) + 30 kB for shell code, checked on every push by `ops/ci/check_bundle_budget.mjs` after `next build`. The original 90 KB was unachievable: the framework alone is 103 kB, and the Feature 01 placeholder loaded 165 kB with the eager Sentry SDK (+59 kB). The Sentry browser SDK now loads after idle, not in the first-load bundle (A1).
- Images: plain `<img srcset>` against the pre-sized variants from Feature 06. **Next.js image optimisation is disabled** (`images.unoptimized`): it would re-encode photos on the shared VM's CPU, which Feature 06 already did once.

### 8. Accessibility baseline
- WCAG 2.2 AA: contrast (§1), visible focus rings (`:focus-visible`, 3:1), keyboard-operable comboboxes and sliders, focus trapped in sheets and returned to the trigger on close, `aria-live` on toasts (polite; errors assertive) and result counts
- Target size: ≥ 24×24 px for every control (WCAG 2.2 SC 2.5.8), ≥ 44×44 px for primary mobile actions (save, contact, call, filter)
- `prefers-reduced-motion` disables sheet, gallery and skeleton shimmer animations
- Form fields always have visible labels. Errors are linked with `aria-describedby`.

### 9. Component gallery and automated checks
- **`/dev/components`** (only when `ENABLE_COMPONENT_GALLERY=1`: local, CI e2e, staging; 404 otherwise, since staging is a production build too, A3) renders every component in every state: default, hover/focus, disabled, loading, error, empty, long content
- **Playwright screenshot tests** of the gallery at 375 and 1280 px, plus `ListingCard` at 320/375/768/1280. Baselines are committed, rendered on Linux in the pinned Playwright image (A12); a diff fails CI. e2e runs against `next build && next start`, not `next dev` (A3). Uses the fixture `page` (Feature 01 §14 context-leak rule).
- **axe-core** runs on the gallery and the shell pages in the e2e job, failing on serious/critical violations. Lighthouse runs in the nightly workflow (A13).
- Vitest + Testing Library for `useApiForm` and the problem→UI table. Web coverage includes `components/**`; the pure modules are gated at 100% (A14)

### 10. Copy and locale
- en-GB only. All money, mileage, dates and distances go through Feature 01 §13's `lib/format`. No component formats them itself.
- Strings live in components (no i18n framework), but user-facing copy for errors is centralised in `problem-ui.ts` so it can be reviewed in one place.

---

## Key Decisions

**Mobile-first is enforced, not aspirational.** Every component is reviewed at 375px
before desktop. The filter panel is a full-screen sheet on mobile and a sidebar from
`lg:` upward.

**One component library for both surfaces.** The dealer portal looks visually
distinct only through layout and nav. Sharing components halves the polish work.

**Public HTML is never personalised.** Rejected: per-user SSR with a Cloudflare
cache-bypass-on-cookie rule. That needs a paid-plan feature or careful Cache Rules,
and a single misconfiguration serves one user's account menu to everyone. Rendering
public HTML identically and hydrating personal islands client-side makes the leak
structurally impossible, and keeps the cache hit rate high.

**Problem codes map to UI in one table.** Rejected: each feature handling 409/429/503
itself. Feature 05's merge prompt, Feature 10's rate-limit message and Feature 12's
"valuation unavailable" would otherwise be built three different ways, and at least
one would end in a raw error or an endless spinner.

**A headless a11y library for complex widgets.** Comboboxes, sliders and dialogs are
where hand-built components fail keyboard and screen-reader users. React Aria
Components gives tested behaviour; Tailwind keeps the look ours.

**No Next.js image optimisation.** The images are already resized once into WebP
variants (Feature 06) and served from Cloudflare. Re-optimising on request would burn
the shared VM's CPU for no gain.

**A `/dev/components` gallery page plus screenshot tests**, instead of Storybook. It's
the cheapest way to catch visual regressions without a separate toolchain.

## Acceptance Criteria

**Components & gallery**
- `/dev/components` renders every component in default, hover/focus, disabled, loading, error and empty states, and returns 404 in a production build
- `ListingCard` renders correctly at 320, 375, 768 and 1280px with a long title, a missing image and a 7-digit price (screenshot tests)
- Gallery screenshot tests at 375 and 1280px run in CI and fail on an unapproved visual diff
- Every text/background token pairing meets AA contrast (token test)

**Errors, forms & states**
- A 422 Problem with `errors[]` puts each message on its field; an error for an unknown field shows as a form-level error
- Double-clicking submit sends one request; the same `Idempotency-Key` is reused if the user retries after a network error
- A 409 `stale_update` opens `ConflictDialog`; "Re-apply mine" re-submits with the new token and succeeds
- A 429 shows the `Retry-After` countdown; a 503 `integration_unavailable` shows the "continue manually" variant; a request hanging past 10 s shows the error state with retry
- `safeNextPath('https://evil.example')` (and every other hostile form) returns `/`; the sign-in redirect e2e is Feature 04's (A10)
- 404, 410 and 500 pages are branded, and the 404 and 500 responses carry `Cache-Control: no-store`
- The exported maintenance page renders with no JavaScript and no external requests

**Caching & performance**
- A public page fetched with and without a session cookie returns identical HTML apart from the CSP nonce
- A file under `web/app/(public)/` importing the cookie-forwarding API client fails CI
- `/dealer`, `/account` and `/admin` responses carry `Cache-Control: private, no-store` and `X-Robots-Tag: noindex`
- The public shell's first-load JS is within the measured floor + 30 KB gzipped (CI size check, A1)
- No CSP violation is logged on any shell page under Feature 01 §11's policy
- The header's signed-in/out slot causes CLS < 0.01

**Accessibility**
- Keyboard-only: you can tab through the header, open the filter sheet, operate the price slider and close the sheet, with focus returning to the trigger
- axe-core reports zero serious or critical violations on the gallery and shell pages; Lighthouse accessibility is 95 or higher
- No page horizontally scrolls at 320px, and primary mobile actions are at least 44×44 px
- With `prefers-reduced-motion: reduce`, the sheet opens without animation

---

## Scale review — what was added, and what was deliberately deferred

**Added (P0/P1), with their sections:**
- P0: public HTML identical for every visitor, cookie-free public API client, personal data only in client islands (§6)
- P0: shared `useApiForm` plus a single Problem-code → UI table (409/429/503/401/403/404/5xx), bounded request timeouts, no unbounded spinners (§3)
- P0: first-load JS budget for the shell, enforced in CI (§7)
- P1: error responses never cacheable (§4)
- P1: branded 404/410/500/global-error pages and a matching static maintenance page (§4)
- P1: React Aria primitives for complex widgets (§2)
- P1: CSP-compatible styling (no runtime CSS-in-JS) and no Next image optimisation (§7)
- P1: WCAG 2.2 target sizes, reduced motion and focus management (§8)
- P1: screenshot tests and axe-core in CI (§9)
- P1: open-redirect-safe `next` handling (§3)
- P1: offline banner (§3)
- P1: contrast-checked tokens (§1)

**Ownership moves:** branded 404/410/500 pages and the global error boundary move here
from Feature 15, which now audits them as part of its states pass.

**Deferred (P2):**
| Item | Trigger to revisit |
|---|---|
| Dark theme | Analytics show > 30% of sessions with `prefers-color-scheme: dark` and a design review agrees |
| i18n framework (externalised strings) | A non-English market or Welsh-language requirement is in scope |
| PWA / service worker / offline caching | Native apps are deprioritised and repeat-visit mobile usage justifies it |
| Storybook | More than one person working on UI components at once |
| Hosted visual-regression service (Chromatic/Percy) | Screenshot baselines in the repo become a merge-conflict bottleneck |

**Scale traps to avoid:** a separate design system per surface (consumer vs dealer);
per-user SSR on cached public pages.
