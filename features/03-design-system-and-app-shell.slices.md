# Feature 03 — Delivery Slices

Design: [03-design-system-and-app-shell.md](03-design-system-and-app-shell.md)
(the *what*). How we build: [IMPLEMENTATION_PLAYBOOK.md](IMPLEMENTATION_PLAYBOOK.md).
This file is the *order and size* of the work. One slice per session; each ends green on
`main` (playbook §1).

**Total:** 14 slices, about 25 h. The design doc says 13 h realistic. The increase comes
from things found while planning (A1–A3, A12): the shell is already over its JS budget,
the CSP blocks the style attributes React Aria renders, the e2e job runs `next dev` and so
cannot prove any header, CSP or bundle criterion, and screenshot baselines have to be
rendered on Linux. Each of these is a guard the design assumed was already there.

| # | Slice | Est. | Depends on | Status |
|---|---|---|---|---|
| 3.1 | Tokens, font, contrast test, web coverage scope | 1.5 h | — | Done (2026-10-20) |
| 3.2 | Production-mode e2e harness and CSP fixes | 1.5 h | — | Built (2026-10-20); awaiting the first CI e2e run |
| 3.3 | First-load JS budget and lazy Sentry | 1.5 h | 3.2 | Not started |
| 3.4 | Public vs session API clients, boundary check, private headers, safe `next` | 1.5 h | 3.2 | Not started |
| 3.5 | Problem contract: typed codes, `ApiError` extensions, mutations, timeout, `problem-ui` | 2 h | 3.4 | Not started |
| 3.6 | Component gallery and basic primitives | 2.5 h | 3.1, 3.2 | Not started |
| 3.7 | React Aria foundation: Modal/Sheet, Toast, Tabs, Accordion | 2 h | 3.6 | Not started |
| 3.8 | Combobox and RangeSlider | 2 h | 3.7 | Not started |
| 3.9 | States, offline banner, `Retry-After` countdown | 1.5 h | 3.5, 3.6 | Not started |
| 3.10 | `useApiForm`, `ConflictDialog`, form-probe endpoint | 2.5 h | 3.5, 3.7, 3.9 | Not started |
| 3.11 | Layouts and the public shell | 2 h | 3.4, 3.7, 3.9 | Not started |
| 3.12 | `ListingCard`, image placeholder, save-heart island | 1.5 h | 3.6, 3.11 | Not started |
| 3.13 | Branded error pages, `Gone`, maintenance page export | 1.5 h | 3.9, 3.11 | Not started |
| 3.14 | Visual regression, axe, keyboard journey, Lighthouse, docs | 2 h | all | Not started |

3.1 and 3.2 have no dependency on each other. 3.3 and 3.4 both only need 3.2. 3.12 and
3.13 can go in either order.

---

## Design amendments (made while planning; applied to the design doc)

- **A1.** **The 90 KB shell budget is already exceeded, before any Feature 03 code.** A
   production build of the Feature 01 placeholder page (`.next/next-bak`, 2026-10-19)
   loads **~160 KB gzipped** of first-load JS: `react-dom` alone is 53 KB, and one chunk
   holding the Next runtime plus the Sentry client is 102 KB. No component work can bring
   that under 90. So the budget is redefined in 3.3: measure the framework floor (Next +
   React, Sentry removed), set the budget at **floor + 30 KB for our shell code**, and load
   the Sentry browser SDK after the page is idle instead of in the first-load bundle (an
   inline nonce'd stub queues errors thrown before it arrives). The measured numbers go into
   the design doc, and Feature 13's 150 KB detail-page budget is re-checked against the
   same floor. *(Open decision 1.)*
- **A2.** **The CSP blocks every server-rendered `style` attribute.** `style-src 'self'
   'nonce-…'` covers attributes too, and nonces never apply to attributes. React Aria
   server-renders them (the visually hidden native `<input>` inside Checkbox, Radio and
   Switch, slider thumb positions, overlay positioning), and React does not re-apply them on
   hydration, so the hidden inputs would show up as raw checkboxes. Today's
   `app/global-error.tsx` is built entirely from inline styles and is already broken under
   this policy. The policy becomes `style-src-elem 'self' 'nonce-…'` plus
   `style-src-attr 'unsafe-inline'`, with `style-src` kept as the fallback. Style
   attributes cannot run script, and any `url()` inside one is still governed by
   `img-src`/`font-src`. `global-error.tsx` imports a stylesheet instead of using inline
   styles. Design §7's "without `unsafe-inline`" now means stylesheets and `<style>`
   elements. *(Open decision 2.)*
- **A3.** **e2e runs against a production build, and the gallery has its own flag.**
   The e2e job runs `next dev`, whose CSP adds `'unsafe-eval'` and whose caching headers,
   chunks and error overlay differ from production. No CSP, `Cache-Control`, bundle or
   screenshot criterion can be proven there. e2e now runs `next build && next start`.
   "404 in a production build" cannot key off `NODE_ENV`, because staging is a production
   build too. `/dev/components` renders only when the runtime env var
   `ENABLE_COMPONENT_GALLERY=1` is set (local, CI e2e, staging) and calls `notFound()`
   otherwise. A test proves the 404 without the flag.
- **A4.** **Two server API clients, and a transitive boundary check.** Today
   `getServerApi` always forwards the session cookie, so design §6's cookie-free
   `apiPublic` does not exist. Split `lib/api/server.ts` into `getPublicApi` (forwards
   request id, trace and client-IP headers, never `cookie` or `authorization`) and
   `getSessionApi` (today's behaviour, renamed so a grep shows every caller). Both import
   `server-only`. The CI check walks the import graph *transitively* from every file under
   `web/app/(public)/`. A direct-import-only rule would pass the moment a shared component
   imports the session client.
- **A5.** **Problem codes are a typed contract between API and web.** Design §3 maps
   `rate_limited` and `integration_unavailable`, but neither exists in `ProblemCode`
   (`backend/app/core/errors.py`). The API has only `dependency_unavailable`, used by the
   readiness probe and DB timeouts. Both codes are added now; Features 04, 05 and 12 raise
   them. `ProblemCode` is exported as an OpenAPI enum, so `problem-ui.ts` is a
   `Record<ProblemCode, …>`: a new backend code then fails the web typecheck until it has
   UI. `dependency_unavailable` maps to the generic retryable `ErrorState`.
- **A6.** **`ApiError` keeps what the UI needs.** `toApiError` drops the `Retry-After`
   header and every RFC 9457 extension member, including `current` on a 409
   `stale_update`, which `ConflictDialog` needs to show what changed. `ApiError` gains
   `retryAfterSeconds` and `extensions`. Timeouts and network failures become their own
   classes (`ApiTimeoutError`, `ApiNetworkError`), so the UI can tell "offline" from "slow"
   from "the server said no".
- **A7.** **The typed client is GET-only.** `lib/api/types.ts` reads only `get` operations,
   so no form can be typed. 3.5 adds method-aware path, body and response types and a
   `mutateClientApi(method, path, body, options)`. The 10 s timeout is the browser client's
   default (`AbortSignal.timeout`); SSR keeps its 3 s.
- **A8.** **What the shell cannot know yet becomes a prop or slot, wired by the owning
   feature.** The header account slot calls `GET /users/me`, which arrives with Feature 04;
   until then the path is absent from the contract and the island renders signed-out. The
   other cases: "Value my car" visibility (Feature 12's flag; no public flags endpoint
   exists), footer make links (Feature 13), the dealer approval banner (Feature 04's dealer
   context) and save-heart behaviour (Feature 09). `ListingCard` takes a `ListingCardData`
   view model defined here, not a generated API type. Feature 07 defines the search
   response and maps it onto the view model.
- **A9.** **A 410 needs a mechanism, and Next has none built in.** The App Router has
   `notFound()` (404) and no `gone()`, and a page cannot change its status once streaming
   starts. 3.13 ships the `Gone` component and time-boxes a 30-minute spike: a middleware
   rewrite to a Gone route with `status: 410`. If Next honours it, Feature 08 uses that
   route. If not, the finding goes into Feature 08's doc as an open problem, since its
   status table depends on it. *(Open decision 4.)*
- **A10.** **The safe `next` rule is a pure function here; the sign-in page is Feature 04.**
   No sign-in route exists yet, so the AC "`next=https://evil.example` lands on the home
   page" is split. 3.4 ships `safeNextPath()` with an exhaustive hostile-input table, and
   Feature 04's sign-in e2e covers the redirect itself.
- **A11.** **The maintenance page is generated into `ops/nginx/`, not `web/public/`.**
   nginx serves it from `/etc/nginx/autotrader` (runbook `network-proxy.md`) when Next is
   down, so a copy under `web/public/` would be served by the process that has failed.
   `web/scripts/build-maintenance.tsx` renders the page with `renderToStaticMarkup`,
   compiles only the Tailwind classes it uses, inlines that CSS and writes
   `ops/nginx/maintenance.html`, which is committed. CI fails if the committed file is
   stale, as it does for the API types. It uses the system font stack, because a font
   request is an external request. nginx adds `Content-Security-Policy: default-src 'none';
   style-src 'unsafe-inline'` on that location.
- **A12.** **Screenshot baselines are rendered on Linux.** Font rasterisation differs
   between Windows and the Ubuntu runner, so baselines made on this machine would fail CI.
   `npm run e2e:snapshots` runs the visual specs inside the pinned
   `mcr.microsoft.com/playwright:v1.64.1-noble` image (it matches `@playwright/test`), and
   a `workflow_dispatch` job does the same and uploads the PNGs as an artifact, for when
   Docker does not fit in memory (playbook §7). Visual specs are tagged `@visual`. *(Open decision 5.)*
- **A13.** **Lighthouse runs nightly; axe runs on every push.** A Lighthouse run per push
   doubles the e2e job's time and memory. The accessibility score is a slow-moving signal.
   axe on every push catches the regressions that matter.
- **A14.** **Web coverage measures components.** `vitest.config.mts` covers only
   `lib/**/*.ts`, so every `.tsx` file and hook would sit outside the report. Coverage now
   includes `components/**` and `lib/**/*.tsx`. The pure modules `lib/api/problem-ui.ts`,
   `lib/forms/**` and `lib/navigation/safe-next.ts` get the same 100% gate as `lib/format`.
- **A15.** **Only our tokens exist as Tailwind colours.** Tailwind v4's default palette is
   switched off (`--color-*: initial`), so `text-gray-500` produces no CSS, and every
   colour on the page is a token the contrast test has checked. Tokens are hex, so the test
   can parse them without a colour library.
- **A16.** **Error responses stay `no-store` after Feature 13 adds edge caching.** Because
   the nonce makes every route dynamic, Next already sends `no-store` today, so the AC
   passes trivially. The real risk comes later: a blanket `s-maxage` set in middleware or
   `next.config` headers applies to every status, including a 500, and Cloudflare would
   cache it. The 3.13 tests assert `no-store` on 404 and 500 for *public* routes, so they
   fail the day Feature 13 adds caching that way. Feature 13 has to set the public cache
   header where the status is known.

---

## Slice 3.1 — Tokens, font, contrast test, web coverage scope (1.5 h)

**Goal:** one set of design tokens, with a test that refuses any text pairing below AA.

**Build**
- `web/styles/tokens.css`: Tailwind v4 `@theme` with the default palette cleared (A15).
  Ink/surface neutral scale, one brand accent, semantic success/warning/danger/info, price
  indicator `great/good/fair/high/none`, focus ring. Also spacing, radius, shadow, and
  named z-index (`header`, `sheet`, `modal`, `toast`). Hex values only.
- `web/styles/pairings.ts`: every foreground/background pairing used for text or UI
  boundaries, each tagged `body` (4.5:1), `large` (3:1) or `ui` (3:1).
- `globals.css` rewritten on the tokens. The Feature 01 grid background, `.status-pulse`
  and the `--signal/--paper` variables go. `prefers-reduced-motion` stays global.
  `font-variant-numeric: tabular-nums` utility for prices and mileage.
- Font: keep Archivo via `next/font/local` (Feature 01), with `adjustFontFallback` so the
  swap causes no layout shift.
- `BRAND` constant (`web/lib/brand.ts`): product name and wordmark, used by every layout,
  the maintenance page and metadata, so a rename is one line. *(Open decision 6.)*
- `vitest.config.mts`: coverage scope per A14.

**Tests that prove it**
- `styles/tokens.test.ts`: parses `tokens.css`, resolves each pairing and asserts its WCAG
  ratio. Fails if a pairing names an unknown token, or if a text-colour token appears in no
  pairing.
- Negative proof: a deliberately low-contrast pairing fails the test; a token written as
  `oklch()` fails the parser.
- A component using `text-gray-500` produces no CSS rule in the build (the A15 guard,
  checked once by hand and recorded in the notes).

**Done when:** gate green (playbook §6); slice committed and pushed.

**Notes (done 2026-10-20):**
- 32 colour tokens in `web/styles/tokens.css`: 9 neutrals, 4 brand, 8 semantic (strong +
  tint), 10 price-indicator, focus. 36 pairings in `styles/pairings.ts`, all AA. The lowest
  are `border-strong` on `canvas` at 3.40:1 (`ui`) and `ink-subtle` on `canvas` at 4.69:1
  (`body`). `line` is the only decorative token, so it is never a control's sole boundary.
- Radius, shadow and font namespaces are cleared too, not only colour, so `shadow-2xl` and
  `rounded-3xl` do not exist either. Tailwind v4 has no z-index namespace, so the named
  layers are `@utility` classes (`z-header` 30, `z-sheet` 40, `z-modal` 50, `z-toast` 60).
  `figures` is the tabular-nums utility; `shell` is the page container (16 px gutters).
- The test also bans colour outside the tokens: Tailwind arbitrary colour values
  (`text-[#…]`, `shadow-[…rgba(…)]`, `bg-[var(--…)]`) in `.ts/.tsx`, and colour literals in
  any stylesheet but `tokens.css`. That is the second half of A15: clearing the palette
  alone would leave arbitrary values as a way round it. Feature 01's pages used both forms
  and are moved onto token classes. The grid background and readiness pulse are gone.
- Guards proven, each by a deliberate violation that failed the test: a low-contrast token
  value, an unpaired token, an `oklch()` token, an arbitrary colour in a component, and an
  uncovered function in `contrast.ts` (100% gate). Compiling `globals.css` with a probe file
  confirmed `text-gray-500` and `bg-white` produce no CSS, while `bg-transparent`,
  `text-current` and every token and named utility do.
- Font: Archivo via `next/font/local` with `adjustFontFallback: "Arial"` set explicitly.
- `BRAND` (`web/lib/brand.ts`) still holds "Autotrader": choosing the public name is open
  decision 6, a product call, so this slice only makes it a one-line change. Used by the
  root metadata and the home page header so far.
- Coverage now measures `lib/**/*.{ts,tsx}`, `components/**` and `styles/**` (A14).
  `styles/contrast.ts` is gated at 100% like `lib/format`.
- `next build` was not run locally (0.7 GB free, playbook §7). CI's `web` job builds; the
  CSS was verified by compiling it through `@tailwindcss/postcss` directly.

---

## Slice 3.2 — Production-mode e2e harness and CSP fixes (1.5 h)

**Goal:** every later slice's header, CSP and visual criterion runs against the real
production server.

**Build**
- `playwright.config.ts`: the web server becomes `npm run build && npm run start` (A3).
  CI builds once and the e2e job reuses the build artifact from the `web` job if that fits
  the workflow; otherwise it builds in the e2e job. `ENABLE_COMPONENT_GALLERY=1` is set for e2e.
- `e2e/fixtures.ts`: an extended `test` whose `page` fixture records
  `securitypolicyviolation` events (via an init script) and console CSP errors, and fails
  the test on any. Every spec imports `test` from here, never from `@playwright/test`
  (oxlint `no-restricted-imports` rule for `e2e/**`). Fixture `page` only (Feature 01 §14).
- `middleware.ts`: the CSP split from A2 (`style-src-elem`, `style-src-attr`).
- `app/global-error.tsx`: inline styles replaced by an imported stylesheet.

**Design / security notes**
- `style-src-attr 'unsafe-inline'` is the only relaxation. `script-src` is unchanged, and
  the CSP header test asserts the exact directive list, so a later widening shows up in a diff.

**Tests that prove it**
- Existing `foundation.spec.ts` passes on the production server.
- Negative proof: a temporary page with a `<style>` element without a nonce fails the
  fixture; a server-rendered `style=""` attribute does *not* (A2 working as intended).
- Unit test of `buildContentSecurityPolicy` asserting the directives.
- Real process: `next build` and `next start` run locally once (check free RAM first,
  playbook §7). If the build is OOM-killed locally, record it and rely on CI for the build.

**Notes (built 2026-10-20):**
- e2e serves the **standalone** server (`node .next/standalone/server.js`), which is what
  systemd runs in production, rather than `next start`, which Next does not support with
  `output: "standalone"`. `scripts/prepare-standalone.mjs` copies `.next/static` and
  `public/` into the standalone tree. `npm run build:standalone` is now the single build
  path for `deploy.sh` (replacing its inline `cp` lines) and the CI e2e job, which builds in
  its own step and runs Playwright with `E2E_SKIP_BUILD=1`.
- `e2e/csp.spec.ts` proves the environment as well as the policy: `'unsafe-eval'` is absent
  from the CSP header, and `next dev` always adds it. A run that silently fell back to a dev
  server therefore fails.
- CSP built in `lib/security/csp.ts` (pure, unit-tested against the exact directive list,
  so any widening shows in a diff); `middleware.ts` only supplies the nonce and env.
- The guard: `e2e/fixtures.ts` extends `test` with an auto fixture that records
  `securitypolicyviolation` events through an init script and an exposed binding. Both are
  injected over CDP, so the policy under test cannot block the guard. Every test fails on
  any violation unless the spec sets `allowCspViolations`. oxlint `no-restricted-imports`
  bans importing `test`/`expect` from `@playwright/test` in `e2e/**` (probe spec rejected;
  `fixtures.ts` exempt).
- Negative proof is permanent rather than a one-off: `/dev/csp-probe` renders an un-nonced
  `<style>` and a server-rendered style attribute. The spec asserts the guard saw exactly
  one `style-src-elem` violation and none for attributes, and that the browser really
  dropped the element's rule while applying the attribute.
- `lib/dev/gallery.ts` (`galleryEnabled`, exact `"1"` only) landed here for the probe;
  3.6's gallery reuses it. `/dev/*` pages call `notFound()` without the flag and are
  `force-dynamic`, so the check runs per request, not at build.
- `global-error.tsx` imports `globals.css` and uses token classes, with no inline styles.
- **Not run locally:** `next build` and the e2e suite (0.2–0.35 GB free, playbook §7).
  Typecheck, lint, unit tests and `playwright test --list` pass. The first real proof of
  this slice is CI's e2e job; until it is green, 3.2 is Built, not Done.

---

## Slice 3.3 — First-load JS budget and lazy Sentry (1.5 h)

**Goal:** the shell's JS cost is measured on every push against a number we can actually hit.

**Build**
- `ops/ci/check_bundle_budget.mjs`: reads `.next/app-build-manifest.json` after
  `next build`, gzips (level 9) each JS chunk of each public route's first load and sums
  them. It fails over budget, prints a per-chunk table, and writes the totals to the job
  summary. The polyfill chunk (`nomodule`) is excluded and documented.
- Measure the floor (A1): a build with Sentry removed from `instrumentation-client.ts`.
  Record per-route totals in the slice notes. Set `SHELL_BUDGET_KB = floor + 30`.
- Lazy Sentry: `instrumentation-client.ts` installs a tiny error/rejection queue and loads
  `@sentry/nextjs` with a dynamic `import()` on `requestIdleCallback` (falling back to a
  timeout). The queue is flushed into Sentry on init. Router-transition tracing starts
  after init. The `beforeSend` scrubbing is unchanged.
- CI `web` job: run the budget check after `npm run build`.

**Tests that prove it**
- An error thrown before the SDK loads reaches Sentry's transport once it loads (vitest
  with the transport stubbed: Sentry is third-party, so a stub is allowed here).
- Negative proof: importing a large dependency into the root layout fails the budget check.
- Record before/after totals in the notes; update design §7 and Feature 13's budget line
  with the measured numbers.

---

## Slice 3.4 — Public vs session API clients, boundary check, private headers, safe `next` (1.5 h)

**Goal:** public HTML cannot be personalised, structurally.

**Build**
- `lib/api/public.ts` (`getPublicApi`) and `lib/api/session.ts` (`getSessionApi`) per A4;
  `server.ts` removed. Header lists live in one module and are tested.
- Route groups: `app/(public)/` (move `page.tsx` here), and empty `app/dealer/`,
  `app/account/`, `app/admin/` layouts so the header rules have routes to test.
- `ops/ci/check_web_boundaries.mjs`: walks imports transitively from every file under
  `app/(public)/` (TypeScript resolver, `@/` alias) and fails on any path that reaches
  `lib/api/session.ts`. It reuses `check_web_fetch.mjs`'s TypeScript loading. Wired into
  CI and the gate.
- `middleware.ts`: `/dealer`, `/account`, `/admin` responses get
  `Cache-Control: private, no-store` and `X-Robots-Tag: noindex`.
- `lib/navigation/safe-next.ts`: `safeNextPath(raw): string` returns a same-origin
  relative path or `/` (A10).

**Tests that prove it**
- Boundary probes: a `(public)` page importing the session client directly fails; one
  importing a component that imports it fails; a `(public)` page using `getPublicApi`
  passes.
- `getPublicApi` sends no `cookie` header to the API even when the browser request carried
  one: an e2e request to a public page, with the API's received headers observed through
  the request-id log line or a test-only echo. Use the real API, not a mock.
- e2e: a public page fetched with and without a session cookie returns identical HTML once
  nonces are normalised. If Sentry or Next puts per-request values into the HTML, list them
  in the notes and normalise them explicitly.
- Header test on all three private prefixes.
- `safeNextPath` table: `https://evil.example`, `//evil`, `/\evil`, `%2F%2Fevil`,
  `javascript:alert(1)`, embedded tab/newline, `/ok?x=1#y` (kept), empty, very long. 100%
  coverage.

---

## Slice 3.5 — Problem contract: typed codes, `ApiError` extensions, mutations, timeout, `problem-ui` (2 h)

**Goal:** every API failure has exactly one UI, decided in one file, checked by the compiler.

**Build**
- Backend: `ProblemCode.RATE_LIMITED`, `INTEGRATION_UNAVAILABLE`; `ProblemCode` exported
  as an OpenAPI enum and referenced from `ProblemDetails.code`. Regenerate
  `openapi.json`/`schema.d.ts` (A5).
- `lib/api/error.ts`: `retryAfterSeconds` (delta-seconds or HTTP-date, capped at 1 h),
  `extensions`, `ApiTimeoutError`, `ApiNetworkError` (A6).
- `lib/api/types.ts` + `lib/api/client.ts`: method-aware types and `mutateClientApi`; a
  default 10 s timeout on browser calls, combinable with a caller's signal
  (`AbortSignal.any`) (A7).
- `lib/api/problem-ui.ts`: `Record<ProblemCode, ProblemUi>` plus status-level fallbacks
  (401, 403, 404, 5xx, timeout, network). Each entry is a kind (`field-errors`,
  `conflict`, `rate-limited`, `unavailable`, `sign-in`, `permission`, `not-found`,
  `retryable`) plus its en-GB copy. All error copy lives here (design §10).
- `fetch` boundary (`check_web_fetch.mjs`) still passes: only `lib/api/` calls `fetch`.

**Tests that prove it**
- Adding a member to `ProblemCode` without a `problem-ui` entry fails `npm run typecheck`
  (probe, then revert).
- Backend: the OpenAPI snapshot shows the enum. The contract freshness check passes after
  regeneration and fails before it.
- `toApiError`: `Retry-After` as seconds and as a date; garbage ignored; `current`
  preserved in `extensions`.
- Timeout: a request that never resolves rejects with `ApiTimeoutError` at 10 s (fake
  timers); a caller abort still wins.
- 100% coverage of `problem-ui.ts`.

---

## Slice 3.6 — Component gallery and basic primitives (2.5 h)

**Goal:** the plain components, each visible in every state on one page.

**Build**
- `app/dev/components/page.tsx` gated by `ENABLE_COMPONENT_GALLERY` (A3), one section per
  component, every state (default, hover/focus forced via a `data-state` prop, disabled,
  loading, error, empty, long content). Sections are anchored, so screenshot tests can
  target one at a time.
- `components/ui/`: Button (variants, sizes, loading with bounded spinner), IconButton
  (required accessible name in its props type), Input, Select (native `<select>`: fine on
  mobile, no React Aria needed), Checkbox, RadioGroup, Toggle, Card, Badge (incl.
  "Example listing", "Reserved", "Sold"), Tag, Skeleton (shimmer off under reduced
  motion), Pagination, Breadcrumbs.
- Labelled-field wrapper: visible label, hint, error linked with `aria-describedby`,
  `aria-invalid`.
- Target sizes: 24×24 minimum for every control; a `size="touch"` (44×44) used for primary
  mobile actions.

**Design notes**
- Server components by default. Only components with state are `'use client'`.
- Checkbox, RadioGroup and Toggle use React Aria here or in 3.7. Either way, the 3.2 CSP
  fixture covers them.

**Tests that prove it**
- `/dev/components` returns 404 with the flag unset (e2e against a second `next start`
  without the env var, or a server-component unit test of the gate).
- Testing Library: label association, `aria-invalid`/`aria-describedby` on error,
  IconButton without a name is a type error (`@ts-expect-error` test).
- e2e smoke: the gallery renders with zero CSP violations (fixture).

---

## Slice 3.7 — React Aria foundation: Modal/Sheet, Toast, Tabs, Accordion (2 h)

**Goal:** overlays and live regions with correct focus and announcements.

**Build**
- Add `react-aria-components` (exact version pin, playbook §5).
- `components/providers.tsx` (client): `I18nProvider locale="en-GB"`, so SSR and the
  browser format numbers identically and hydration never mismatches on a slider label. Also
  `RouterProvider` bound to Next's router, so React Aria links navigate client-side. And
  the toast queue.
- Modal and Sheet (bottom sheet below `lg`, side panel from `lg`), focus trapped and
  returned to the trigger, `Escape` closes, scroll locked, named z-index layers.
- Toast: one global region; polite by default, assertive for errors; max 3 visible;
  deduplicated by message. React Aria's toast API is `UNSTABLE_`, so it sits behind our
  `useToast()`, and a later API change touches one file.
- Tabs, Accordion.
- Animations through CSS classes only (CSP), and disabled under reduced motion.

**Tests that prove it**
- Testing Library + user-event: focus moves into the sheet, `Tab` stays inside it, and
  close returns focus to the trigger.
- Toast: the error variant renders in an assertive region; ten identical toasts render once.
- e2e: open the sheet with the keyboard on the gallery under
  `emulateMedia({ reducedMotion: 'reduce' })`. The sheet is fully visible on the first
  frame after opening (no transition running), and no CSP violation is reported.
- Bundle: record the size React Aria adds to the gallery route. The public shell must not
  import Modal, Tabs or Accordion (the budget check from 3.3 would show it).

---

## Slice 3.8 — Combobox and RangeSlider (2 h)

**Goal:** the two widgets most often built wrong, built once.

**Build**
- Combobox (make/model): filter-as-you-type over `items`, an `isLoading` prop, and an
  empty-results message. Accent-insensitive matching (`Citroen` finds `Citroën`), in step
  with Feature 02's lookup normal form. The gallery fixture is a static list of real make
  names, since no taxonomy endpoint exists yet (Feature 05/07).
- RangeSlider: two thumbs, integer steps, values in the caller's unit (pence for price,
  miles for mileage). Labels and `aria-valuetext` go through `lib/format`, never formatted
  inline. Keyboard: arrows, `PageUp`/`PageDown` (10 steps), `Home`/`End`.

**Tests that prove it**
- Combobox: keyboard-only selection; screen-reader roles (`combobox`, `listbox`,
  `aria-activedescendant`); 550 options filter without noticeable lag (render-time
  assertion, generous bound).
- RangeSlider: thumbs cannot cross; `aria-valuetext` reads "£5,000"; each key moves the
  documented amount; SSR markup with thumbs positioned by style attributes produces no CSP
  violation (the A2 case).

---

## Slice 3.9 — States, offline banner, `Retry-After` countdown (1.5 h)

**Goal:** no screen ever ends in a raw error or an endless spinner.

**Build**
- `EmptyState`, `ErrorState` (variants `generic`, `unavailable` "continue manually",
  `offline`; retry action; small `request_id`), `PermissionDenied`, `NotFound`. Each takes
  its copy from `problem-ui.ts`.
- `<ProblemView error={…}>`: renders the right state for any thrown `ApiError` /
  timeout / network error, using the 3.5 table.
- `useRetryAfter(seconds)`: countdown with one `aria-live="polite"` announcement at start
  and at zero, not every second.
- Offline banner: `navigator.onLine` events, plus a module-level signal set by
  `ApiNetworkError` and cleared by the next success. One instance, in the layouts.

**Tests that prove it**
- `ProblemView` table test: every `problem-ui` kind renders its state. 503
  `integration_unavailable` renders the "continue manually" variant.
- Countdown: fake timers, enabled at zero, announced twice in total.
- Offline: dispatching `offline`/`online` toggles the banner; a network error shows it
  while `navigator.onLine` is still true.

---

## Slice 3.10 — `useApiForm`, `ConflictDialog`, form-probe endpoint (2.5 h)

**Goal:** every later form gets validation, double-submit protection, idempotency and
conflict handling for free.

**Build**
- Add `zod` (pinned). `lib/forms/use-api-form.ts`: `useApiForm(schema, submit, options)`.
  It provides client validation; a submit lock (a ref, not state, so a double click in one
  frame is caught); an `Idempotency-Key` generated when the form mounts and reused on
  retry after a network error or timeout, renewed only after a success or a field change
  following a 4xx; 422 `errors[]` mapped onto fields by `field`, with unknown fields as a
  form-level error; values kept on failure. Endpoints that take a key are listed in one
  place.
- `ConflictDialog`: on 409 `stale_update`, shows changed fields (diff of the submitted
  values against `extensions.current`, with labels supplied by the form) and offers "Reload
  theirs" or "Re-apply mine" (re-submits with `current.updated_at`).
- Backend: `POST /api/v1/dev/form-probe`, mounted only when `ENVIRONMENT` is `local`,
  `test` or `ci`. It validates a small body (422 with `errors[]`, including one error on a
  field the form does not have) and holds an `updated_at` token in Redis (409
  `stale_update` with `current`). It can be told to return 503 `integration_unavailable`
  or 429 `rate_limited` with `Retry-After`, and it counts executions per idempotency key.
  It runs behind the real `IdempotencyMiddleware`. *(Open decision 3.)*
- Gallery: a probe form exercising every path.

**Tests that prove it** (design AC *Errors, forms & states*)
- e2e against the real API: a double-click sends one request; a request aborted at the
  network level, then retried, reuses the key and the probe executed once; 422 messages land
  on fields and the unknown field becomes form-level; 409 opens `ConflictDialog` and
  "Re-apply mine" succeeds; 429 shows the countdown; 503 shows "continue manually"; a
  request routed to a hang shows the error state with retry after 10 s.
- Backend: the probe route is absent when `ENVIRONMENT=production` (test the app factory
  with production settings), so it can never ship.
- Unit: key lifecycle rules; 100% coverage of `lib/forms/**`.

---

## Slice 3.11 — Layouts and the public shell (2 h)

**Goal:** the three surfaces' chrome, with personal data only in client islands.

**Build**
- `PublicLayout` (`app/(public)/layout.tsx`): skip link, header (wordmark from `BRAND`,
  search entry linking to `/search` (Feature 07), "Value my car" behind a `showValuation`
  prop defaulting to `false` (A8), "For dealers" link, account slot), footer (legal links,
  a make-links slot for Feature 13). Mobile-first; no horizontal scroll at 320 px.
- Account island (`'use client'`): fixed-size box reserved at SSR. It calls `GET
  /users/me` once that path exists in the contract (Feature 04). Until then it renders
  signed-out without a request (A8). 401/404 render signed-out; other errors show
  signed-out silently.
- `DealerLayout`: side nav from `lg`, bottom nav below (Stock, Leads, Team, Settings), an
  approval banner driven by a `dealerStatus` prop (Feature 04 supplies it).
- `AdminLayout`: minimal.
- Toast region and offline banner mounted once per layout; `loading.tsx` replaced with
  skeletons.

**Tests that prove it**
- e2e: CLS of the header island < 0.01 (`PerformanceObserver` `layout-shift`, island
  response delayed by a route handler).
- e2e at 320 px: `document.documentElement.scrollWidth <= 320` on home, a dealer page and
  the gallery.
- Bottom nav visible below `lg`, side nav from `lg` (two viewports).
- No `(public)` file imports the session client (3.4 check still green).

---

## Slice 3.12 — `ListingCard`, image placeholder, save-heart island (1.5 h)

**Goal:** the most-reused composite, solid at every width and with the worst real data.

**Build**
- `ListingCardData` view model (A8): title, variant, price pence, year, mileage, fuel,
  transmission, location text, optional distance, image variants (`srcset` entries) or
  none, badges (demo, reserved, sold), optional price-indicator slot.
- `ListingCard`: plain `<img srcset sizes loading="lazy">` with a fixed aspect ratio, so no
  CLS; `images.unoptimized: true` in `next.config.ts`. A local SVG placeholder when there
  is no image (Feature 02 A4: demo stock has none until Feature 06). Long titles clamp to
  2 lines. All values through `lib/format`.
- Save heart: a client island with a 44×44 target and a reserved slot. It is a controlled
  `pressed` + `onToggle`, wired to saved cars by Feature 09.

**Tests that prove it**
- Gallery cases: long title, missing image, 7-digit price (`£1,250,000`), demo badge,
  sold, no distance.
- Testing Library: the card's accessible name is the title, and the heart is a toggle
  button with `aria-pressed`.
- Placeholder is served from `'self'` (CSP `img-src` passes with no CDN configured).

---

## Slice 3.13 — Branded error pages, `Gone`, maintenance page export (1.5 h)

**Goal:** failure looks deliberate, and is never cached.

**Build**
- Branded `app/not-found.tsx`, `app/error.tsx` (retry, `request_id` from the digest;
  Sentry capture stays) and `global-error.tsx` (stylesheet-based since 3.2).
- `Gone` component with a "similar cars" slot (Features 08/13). 30-minute spike on the 410
  mechanism (A9), with the result recorded in the notes and in Feature 08's doc.
- `web/scripts/build-maintenance.tsx` → `ops/nginx/maintenance.html` (A11); `npm run
  build:maintenance`; CI freshness check; the CSP `add_header` in `autotrader.conf`.

**Tests that prove it**
- e2e: a missing public route returns 404 branded with `Cache-Control` containing
  `no-store`; a test route that throws returns 500 branded with `no-store` (A16). The
  throwing route exists only behind the gallery flag.
- The maintenance page opened in Playwright with JavaScript disabled and every non-`file:`
  request aborted renders its heading, and zero requests were attempted.
- Freshness: editing the source without regenerating fails the CI check (probe).

---

## Slice 3.14 — Visual regression, axe, keyboard journey, Lighthouse, docs (2 h)

**Goal:** the design bar is held by CI, not by memory.

**Build**
- `@visual` Playwright specs: each gallery section at 375 and 1280 px; `ListingCard` at
  320/375/768/1280. Fonts awaited (`document.fonts.ready`), animations disabled, the
  clock fixed. Baselines committed, generated on Linux (A12): `npm run e2e:snapshots`
  (Docker) and the `workflow_dispatch` snapshot job.
- `@axe-core/playwright` on the gallery and every shell page; fails on serious or critical.
- Keyboard journey e2e: tab through the header, open the gallery's filter-sheet demo,
  operate the price slider, close it, focus is back on the trigger.
- Target-size e2e: every interactive element ≥ 24×24; elements marked `data-touch` ≥ 44×44
  at 375 px.
- `nightly.yml`: Lighthouse (pinned `@lhci/cli`) on home and the gallery, accessibility
  ≥ 95 (A13).
- Docs: design doc status and implementation notes; FEATURES_PLAN status; README
  (gallery flag, snapshot command, maintenance build); playbook §6 gate gains the new web
  checks (boundary, budget, maintenance freshness).

**Tests that prove it**
- Negative proofs: a 2 px padding change fails a screenshot; a button with no accessible
  name fails axe; a 20×20 control fails the target-size test.

**Done when:** e2e (including `@visual`) green on GitHub, and the nightly Lighthouse step
passes once (ask the user to trigger `workflow_dispatch` and check the Actions tab;
playbook §7).

---

## How earlier lessons apply here

| Lesson (playbook) | Where it bites in Feature 03 | What the slice does |
|---|---|---|
| Test against the real thing (§2) | `next dev` differs from production in CSP, headers, chunks | e2e on `next start` (3.2); the form probe runs against the real API and idempotency middleware (3.10) |
| Prove every guard can fail (§2) | contrast test, bundle budget, boundary check, CSP fixture, typed problem table, screenshots, axe | Each slice has a probe that makes its guard fail once |
| Reader/writer agreement (§2) | Backend problem codes vs web UI table; tokens vs pairings | `ProblemCode` as an OpenAPI enum + `Record<ProblemCode,…>` (A5); unpaired token fails (3.1) |
| Enforce future rules mechanically (§3) | "No personal data on public pages", "no unchecked colours" | Transitive import check (A4); default palette removed (A15) |
| Measure, don't assert (Feature 02 §2.9) | The 90 KB budget was never measured | Measured 160 KB; budget redefined from a measured floor (A1) |
| Pin versions (§5) | React Aria's `UNSTABLE_` toast, Playwright image, lhci | Exact pins; toast behind one wrapper |
| Third-party-only mocks (§2) | Sentry transport | Stubbed only there; our API is called for real |
| UTF-8 explicitly (§4) | Generated maintenance page, `Citroën` in the combobox | Explicit encoding in the generator; accent-insensitive filter |
| Memory budget (§7) | `next build`, Docker Playwright, Lighthouse | Single local build per slice; snapshot job in CI as fallback; Lighthouse nightly |
| Destructive/production refusals (§5) | Dev-only gallery and form probe | Both refuse in production, with tests |

---

## Open decisions (defaults chosen; change before the slice starts)

1. **Shell JS budget** (A1, before 3.3): default is a measured framework floor + 30 KB with
   lazy-loaded Sentry. Alternative: keep Sentry eager and accept roughly floor + 85 KB.
2. **`style-src-attr 'unsafe-inline'`** (A2, before 3.2): default allows style attributes
   only. Alternative: no React Aria for checkbox/radio/switch/slider and hand-built
   widgets without inline styles, which design §2 rejects as the most common source of a11y bugs.
3. **Form probe endpoint** (3.10): default is a dev-only backend route, so the
   idempotency and 409 paths are proven against the real middleware. Alternative: unit
   tests with a stubbed `fetch` only. That is faster to write, but it would be the
   `MagicMock` mistake from Feature 01 again.
4. **410 mechanism** (A9, 3.13): default is a 30-minute spike of a middleware rewrite with
   `status: 410`. Whatever the spike finds, Feature 08's doc has to record it.
5. **Snapshot baselines** (A12, 3.14): default is Docker locally, with the CI artifact job
   as fallback. Alternative: CI only.
6. **Product name** (3.1): the public wordmark should not be "Autotrader" on a launched
   beta, because Auto Trader is a registered UK trade mark. Default: `BRAND` holds a
   neutral working name until one is chosen; the repo name can stay. Needed before
   Feature 13 (SEO) and Feature 15 (launch), not before 3.1.
