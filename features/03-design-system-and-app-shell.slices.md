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
| 3.2 | Production-mode e2e harness and CSP fixes | 1.5 h | — | Done (2026-10-21) |
| 3.3 | First-load JS budget and lazy Sentry | 1.5 h | 3.2 | Done (2026-10-21) |
| 3.4 | Public vs session API clients, boundary check, private headers, safe `next` | 1.5 h | 3.2 | Done (2026-10-21) |
| 3.5 | Problem contract: typed codes, `ApiError` extensions, mutations, timeout, `problem-ui` | 2 h | 3.4 | Done (2026-10-21) |
| 3.6 | Component gallery and basic primitives | 2.5 h | 3.1, 3.2 | Done (2026-10-21, branch `feature3`) |
| 3.7 | React Aria foundation: Modal/Sheet, Toast, Tabs, Accordion | 2 h | 3.6 | Done (2026-10-21, branch `feature3`) |
| 3.8 | Combobox and RangeSlider | 2 h | 3.7 | Done (2026-10-21, branch `feature3`) |
| 3.9 | States, offline banner, `Retry-After` countdown | 1.5 h | 3.5, 3.6 | Done (2026-10-21, branch `feature3`) |
| 3.10 | `useApiForm`, `ConflictDialog`, form-probe endpoint | 2.5 h | 3.5, 3.7, 3.9 | Built (2026-10-22, branch `feature3`); Done once CI e2e is green |
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
- **A17.** **RangeSlider is built from React Aria's hooks, not its `Slider` component**
   (found in 3.8). The component formats `aria-valuetext` through `Intl.NumberFormat`
   options, so a value in pence cannot be read as "£5,000" via `lib/format` (§10). It also
   pages by a tenth of the range instead of a fixed step count. The hooks (`useSlider`,
   `useSliderThumb`, `useSliderState`) take a formatter object and a state we can adjust,
   so both hold, still with React Aria's keyboard and screen-reader behaviour.
- **A18.** **An `Idempotency-Key` is reused only for an identical, unanswered request**
   (found in 3.10). The plan said "renewed only after a success or a field change
   following a 4xx". But the API stores and replays every answer below 500. Reusing a key
   after a 429 would replay the 429 forever, and "Re-apply mine" sends a new `updated_at`,
   so the same key would get `idempotency_key_reused`. Rule
   (`lib/forms/idempotency-key.ts`): the key minted at mount is used for the first
   attempt; it is reused only when the previous attempt got no answer (network error or
   timeout) and the payload is identical; any answer spends it.
- **A19.** **zod runs `jitless`, imported only through `lib/forms/zod.ts`** (found in
   3.10). zod 4 probes `new Function` to decide whether to compile parsers. Under our CSP
   the browser blocks it and reports a violation on every page with a schema. `jitless`
   skips the probe; an oxlint `no-restricted-imports` rule makes the wrapper the only
   way in. Cost: the gallery grew 225.8 → 288.6 kB. A public-page form (Feature 09's lead
   form) must check the budget and may need `zod/mini` or server-only validation.

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

**Notes (done 2026-10-21):**
- **Measured** (`next build`, Next 15.5.28, React 19.1.0, gzip level 9, kB of 1,000 bytes as
  `next build` prints them):

  | Build | `/` first load | Shared by all |
  |---|---:|---:|
  | Before (eager Sentry) | 165 kB | 162 kB |
  | Floor (Sentry client stubbed) | 107 kB | 103 kB (Next runtime 46.8, `react-dom` 54.2, other 2.3) |
  | After (lazy Sentry) | **108 kB** | 104 kB |

  The budget is 103 + 30 = **133 kB**. The checker's totals match `next build`'s own column
  to the decimal on both builds, so the two can be compared directly.
- `ops/ci/check_bundle_budget.mjs` reads `app-build-manifest.json`. It sums each page
  route's unique first-load JS chunks, excluding `nomodule` polyfills, and gates the public
  routes (`/dev`, `/dealer`, `/account`, `/admin` are printed but not gated). It writes a
  route table and the heaviest route's chunks to the job summary. It refuses to pass when
  it finds no public routes (a vacuous pass). `BUNDLE_BUDGET_KB` overrides the budget for
  probes. Negative proof: budget 105 on the real build exits 1 naming `/` (107.7 kB); the
  default exits 0. Runs in CI's `web` job after `npm run build`.
- Lazy Sentry: `lib/observability/lazy-sentry.ts` (`startLazySentry`) is called from
  `instrumentation-client.ts`. No inline stub script was needed: `instrumentation-client`
  already runs before hydration from the main bundle, so the queue there catches
  everything an inline script would. The design's "inline nonce'd stub" is dropped. With no
  DSN (local, CI) the SDK is never downloaded. The first queued error triggers the load
  instead of waiting for idle. The queue is capped at 20, and our listeners are removed on
  init because the SDK installs its own (otherwise every error is reported twice).
  Router transitions before init are not traced. 13 tests, file gated at 100%.
- e2e (3.2) ran locally for the first time against the standalone server: both CSP specs
  pass (production policy, guard catches the un-nonced `<style>`, allows style
  attributes). `foundation.spec.ts` failed locally only because Docker Desktop had hung
  (API readiness: db, redis and storage all unavailable; `docker ps` timed out). CI runs it
  on fresh services.
- **Found for later slices:** `/_not-found` is prerendered **static**, so its HTML carries
  no CSP nonce and its scripts would be blocked under `strict-dynamic` (3.13 fixes it with
  the branded 404, and its e2e will catch it). `@sentry/nextjs` enables Next's
  `clientTraceMetadata` experiment, which can write per-request trace `<meta>` tags into
  HTML; 3.4's "identical HTML for every visitor" test must normalise or disable them.
- Local builds take 1.5–10 min and failed twice mid-build at 0.2–0.5 GB free (playbook §7);
  `NODE_OPTIONS=--max-old-space-size=1536` (as `deploy.sh` uses) got them through.

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

**Notes (done 2026-10-21):**
- Clients: `lib/api/public.ts` (`getPublicApi`) and `lib/api/session.ts` (`getSessionApi`),
  both `import "server-only"` (package pinned at 0.0.1). The shared header logic is in
  `lib/api/forwarding.ts`: `CONTEXT_HEADERS` (request id, trace, client-IP chain) and
  `IDENTITY_HEADERS` (`cookie`, `authorization`). `forwardedHeaders` also deletes identity
  headers passed in by the caller, so `getPublicApi(path, { headers: { Cookie } })` cannot
  smuggle one through. `server.ts` is gone, and the home page moved to `app/(public)/`.
- **Real-API proof:** a backend dev router (`app/api/v1/endpoints/dev.py`) is mounted only
  when `ENVIRONMENT=local` and left out of the OpenAPI schema, so the generated web
  contract stays production-only. `GET /api/v1/dev/echo-headers` returns *which* headers
  arrived, never their values. `/dev/api-clients` (gallery flag) calls it through both
  clients with a session cookie set: the public client's request had no cookie, the session
  client's did. Backend tests: absent (404) for `staging`/`production`, present for `local`,
  absent from `/openapi.json`, names-only response. The route checks are behavioural, not
  `app.routes`, because FastAPI mounts included routers lazily. 3.10's form probe goes in the
  same router.
- Boundary check: `ops/ci/check_web_boundaries.mjs` walks static imports, re-exports,
  dynamic `import()` and `require` with TypeScript's resolver (`@/` alias + relative),
  breadth-first, and reports the shortest chain. It runs in CI's `web` job and in
  `make web-check`. `web/lib/api/boundaries.test.ts` runs it on throwaway fixture trees:
  direct import, a three-hop chain through components, a dynamic import, the allowed cases
  and a cycle. A real probe (public page → component → session client) exited 1 with the
  chain. The test loads the checker through Node's `require` (Node ≥ 22.12 can require ES
  modules), because Vite refuses modules outside the web root.
- Private surfaces: `app/dealer`, `app/account`, `app/admin` placeholders whose layouts are
  `force-dynamic`. Middleware sets `Cache-Control: private, no-store` and
  `X-Robots-Tag: noindex` on whole-segment matches (`isPrivatePath`, so `/dealers-near-me`
  stays public). e2e checks all three plus a nested path, and that `/` has no `noindex`.
- Identical HTML: the e2e test normalises the CSP nonce, the response's own `x-request-id`
  (the home page prints it while the API is unavailable), and Sentry's
  `sentry-trace`/`baggage` meta tags. Each is replaced by its exact value, never by a "any
  UUID" pattern, which would also hide a leaked user id.
- `safeNextPath`: refuses anything not starting with a single `/`, any backslash, control
  characters (tab/CR/LF are stripped by browsers, turning `/	/evil` into `//evil`) and over
  2,048 characters, then re-checks after URL normalisation (`/..//evil` → `//evil`). 26
  cases, 100% gate. `lib/api/forwarding.ts` is gated at 100% too.
- Local e2e on the standalone build (Docker down, so the API had no DB): all 7 new specs and
  both CSP specs pass with `--workers=1`. Three parallel workers on 0.8 GB free gave
  timeouts and resets. `foundation.spec.ts` still fails locally only because the API's
  dependencies are down.
- Not proven by a deliberate failure: removing the middleware header block (it would need
  another 2–10 min build). The matcher is unit-tested, and the e2e specs would fail without
  the headers.

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

**Notes (done 2026-10-21):**
- Backend: `ProblemCode` gains `NOT_FOUND`, `RATE_LIMITED`, `INTEGRATION_UNAVAILABLE`.
  `ProblemDetails.code` is typed `ProblemCode`, so the OpenAPI schema exports the enum and
  the web `ProblemCode` is a union. `problem_response` and `AppError` now take
  `ProblemCode` only, not `ProblemCode | str`: a string code bypassed the enum, which is
  the reader/writer gap A5 is about (one test passed `'bad_request'` as a string, fixed).
  429 is documented on every route.
- **Found:** every bare `HTTPException` below 500, including 404 for an unknown route,
  returned `code: bad_request`, so the UI table would have shown "bad request" for a
  missing page. `_code_for_status` now maps 404 to `not_found` (other 4xx stay
  `bad_request`, 5xx `internal_error`).
- `scripts/export_openapi.py` writes with `newline='
'`: on Windows it wrote CRLF
  (playbook §4). Git normalised it, but a local freshness diff would have been noisy.
- `lib/api/error.ts`: `ApiError` gains `retryAfterSeconds` and `extensions` (every
  non-RFC-9457 member, e.g. `current` on a 409). `parseRetryAfter` takes delta-seconds or an
  IMF-fixdate, capped at 1 h and never negative. **Found:** `Date.parse` accepts `"-5"`
  (the year −5) and `"1.5"`, so dates must match the RFC 9110 format before parsing.
  `ApiError.code` stays `string`: a newer API may send a code this build does not know, and
  the UI then falls back on the status.
- `lib/api/response.ts` is the one request path. `timeoutMs` uses its own
  `AbortController` and timer, not `AbortSignal.timeout`, so fake timers can drive it and a
  timeout can be told apart from a caller's abort. Results: `ApiTimeoutError` (our limit),
  `ApiNetworkError` (no response), or the caller's `AbortError` re-thrown unchanged, so a
  cancelled request is never reported. The body is read inside the limit too. Browser
  `getClientApi`/`mutateClientApi` use 10 s; SSR (`forwarding.ts`) uses 3 s through the
  same mechanism, replacing `AbortSignal.timeout`.
- Types: every helper in `lib/api/types.ts` takes the paths interface as a last type
  parameter, so `types.test.ts` checks them against a fixture contract (no mutation
  endpoints exist yet). `ApiPath` is now GET paths only. `mutateClientApi(method, path,
  body, { idempotencyKey })` sets `Content-Type` only when there is a body.
  `assertApiPath` narrows to `/api/v1/${string}` for every method.
- `lib/api/problem-ui.ts`: `PROBLEM_UI: Record<ProblemCode, ProblemUi>` plus status
  fallbacks (401 sign-in, 403 permission, 404, 409, 422, 429, 503, other 4xx invalid, 5xx
  retryable), `TIMEOUT_UI`, `OFFLINE_UI`, and `problemUi(error)`, which also carries
  `requestId` and `retryAfterSeconds`. For the generic codes (`bad_request`,
  `internal_error`) the status decides, so a 403 raised as a bare `HTTPException` shows
  "permission". The lookup uses `Object.hasOwn`, so a code such as `toString` is not
  treated as known (tested).
- Guard proven: adding a member to the generated `ProblemCode` union fails
  `npm run typecheck` at `PROBLEM_UI` (reverted). The backend test asserts the exported
  enum equals the Python enum.
- Coverage: `problem-ui.ts` gated at 100%; every `lib/api` file is at 100% lines.
- Backend not fully run: Docker was down, so the 4 tests that need live Postgres failed
  (connection refused); the other 32 in `test_foundation_api.py`, the problem-contract tests
  and the dev-route tests pass. CI runs the full suite.

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

**Notes (done 2026-10-21, on branch `feature3`):**
- From this slice on, Feature 03 work lives on the `feature3` branch, not `main`.
- 3.2 is Done: CI was fully green at `eb53655` after four CI fixes that were not slice
  work: the xdist race on `roles.sql` (advisory lock on the shared `postgres` database), an
  order-dependent taxonomy test, the pre-commit job that had never run (its prettier pin
  `v3.5.3` did not exist; first repo-wide format in `3915412`), a gitleaks hit on a
  literal test key, and a certifi advisory.
- Components in `web/components/ui/`: `button.tsx` (Button with 4 variants and
  `sm`/`md`/`touch` = 36/40/44 px, `loading` keeps the label and sets `aria-busy`;
  IconButton requires `label`; Spinner), `inputs.tsx` (TextInput, Select, Checkbox,
  Toggle, RadioGroup), `field.tsx` (label/hint/error wiring), `display.tsx` (Card, Badge
  with 7 token tones, `ListingBadges` Example/Reserved/Sold, Tag, Skeleton) and
  `navigation.tsx` (Pagination with a pure `pageItems`, Breadcrumbs).
- **Checkbox, Radio and Toggle are native**, not React Aria. Design §2's React Aria list
  is combobox, slider, dialog/sheet, tabs and toast. Native controls are fully accessible,
  need no script and render no style attributes. Toggle is a checkbox with
  `role="switch"`. The whole label row is the click target (≥ 44 px).
- **No hooks in any component**, so they render the same in server components and in 3.10's
  client forms. Fields take an explicit `id` (no `useId`); hint and error ids derive from
  it. Select is the native `<select>`, the best picker on a phone.
- **Forced states:** `@custom-variant hover-state` / `focus-state` in `globals.css` match
  `:hover` / `:focus-visible` *or* `[data-force~="hover|focus"]`. Components use them, never
  bare `hover:`, so the gallery renders hover and focus deterministically for 3.14's
  screenshots. Verified in compiled CSS. Tailwind's own `hover:` also waits for
  `@media (hover: hover)`; ours does not.
- Gallery `/dev/components`: 10 anchored sections (buttons, icon buttons, text inputs,
  selects, choices, badges, cards, skeletons, pagination, breadcrumbs), each state
  including long content. It is server-only, so it adds **0 kB** of JS (107.8 kB, the same
  as `/`). The section index links are marked `data-inline-link` (SC 2.5.8's inline
  exception). Breadcrumb links got `min-h-6` because they are not inline text.
- Vitest can now render components: the `oxc` JSX runtime (Vite 8 uses oxc, not esbuild),
  the `@/` alias, and Testing Library `cleanup` after each test in `vitest.setup.ts`
  (automatic cleanup needs test globals, which are off).
- Tests: 32 component and gallery unit tests. They cover label, `aria-describedby` and
  `aria-invalid` wiring, a switch role, a named radio group, loading buttons, `type=button`
  by default, and `pageItems` (a one-page gap is shown as the page). An IconButton without
  `label` is an `@ts-expect-error` (if `label` became optional, typecheck would fail on the
  unused directive). The gallery is a 404 without the flag (asserted on the `notFound()`
  digest) and has unique ids. e2e: every section renders, the native controls work, and
  every control is ≥ 24×24 at 375 px, all with zero CSP violations.
- Local e2e: 13 of 14 pass on the standalone build (`--workers=1`). `foundation.spec.ts`
  still fails locally only because Docker is down.

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

**Notes (done 2026-10-21, branch `feature3`)**
- Pinned `react-aria-components` 1.21.1 and `@testing-library/user-event` 14.6.7.
- **The budget check under-counted, and now it doesn't.** A page's entry in
  `app-build-manifest.json` lists only the page's own chunks; the layouts above it are
  separate entries. `next build`'s "First Load JS" column leaves them out too. With the
  providers in the root layout, `/` read 107.8 kB while a first visit really loaded
  130.1 kB (React Aria chunk, 21.1 kB). `check_bundle_budget.mjs` now adds every ancestor
  `layout` entry, so its numbers are higher than Next's table, which is expected.
- **The toast region loads lazily.** `next/dynamic` with `ssr: false` in `providers.tsx`
  takes it out of the first load: `/` is **111.6 kB** (+3.8 kB for the providers and the
  queue) against the 133 kB budget. Toasts only ever follow a user action, and a toast
  raised before the region mounts waits in the queue. To make that split possible,
  `toast.ts` (queue, `showToast`, `useToast`) and `toast-region.tsx` (rendering) are
  separate files. Only those two touch the `UNSTABLE_` API.
- Gallery route: 157.6 kB (107.8 kB → +49.8 kB for Modal, Sheet, Tabs, Accordion and the
  primitives' demos). Not gated; the public shell imports none of them.
- **CSP: React Aria inserts one `<style>` at runtime**, `usePress`'s `touch-action` rule
  (`#react-aria-pressable-style`). Without a nonce the policy blocked it; the 3.2 auto
  fixture caught it on every gallery spec. React Aria reads the nonce from
  `<meta name="csp-nonce">`, so the root layout renders that tag with the per-request
  nonce in its `nonce` attribute (the browser blanks the attribute once parsed, so later
  script cannot read it), never in `content`. Reading `headers()` makes the root layout
  dynamic, so `/_not-found` is now dynamic too and also gets a nonce. That closes the
  static-404 gap noted for 3.13.
- **Toast roles:** React Aria marks every toast `role="alert"`. `ToastContent` overrides it:
  errors are `alert`/assertive, info and success are `status`/polite (§8). Errors have no
  timeout (WCAG 2.2.1); info and success dismiss after 6 s. Duplicates of a visible toast
  are dropped; at most 3 are visible.
- `TriggerButton` (a React Aria `Button` with our `buttonClasses`) exists because
  `DialogTrigger` needs a React Aria pressable; our hook-free `Button` cannot be one.
- Modal and Sheet: `ModalOverlay` locks scroll and traps focus. The sheet is a bottom sheet
  (`max-h-[85dvh]`) below `lg` and a side panel (`lg:w-96`) from `lg`. Enter and exit
  animations are CSS keyframes keyed on `data-entering`/`data-exiting`, turned off by
  `motion-reduce`.
- Tests: 9 React Aria unit tests (focus in, `Tab` trapped, focus restored on Escape, close
  button and footer actions; toast roles, dedupe, max 3, dismiss; arrow-key tabs,
  accordion `aria-expanded`). React Aria restores focus on the next frame, so those
  assertions use `waitFor`. The toast queue is global, so `afterEach` drains it
  completely, or waiting toasts leak into the next test. e2e: the sheet at 375 px under
  reduced motion sits at `bottom: 0` with `transform: none` on the first check, and
  Escape returns focus. Ten identical errors show one alert. Toast assertions are scoped
  to the "Notifications" region, because Next's route announcer is also a
  `role="alert"`. The new CSP spec checks that the pressable style carries the meta's
  nonce and that the meta exposes no nonce in the DOM.
- Guard probes: `BUNDLE_BUDGET_KB=110` fails the budget check on `/` (111.6 kB). Before
  the meta tag, the gallery specs failed on the `style-src-elem` violation.
- Local e2e: 15 of 16 pass on the standalone build. `foundation.spec.ts` still fails only
  because Docker is down locally.

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

**Notes (done 2026-10-21, branch `feature3`)**
- **One lookup normal form, two languages, one contract file.** `lib/format/lookup.ts`
  (`normaliseLookup`, `matchesLookup`) mirrors `normalise_lookup` in
  `backend/app/modules/taxonomy/naming.py`. `ops/contracts/lookup-normal-form.json` holds
  20 cases (accents, `&`/`+`, `ß`, full-width letters, the `ﬁ` ligature, empty input).
  `backend/tests/test_lookup_contract.py` and `lib/format/lookup.test.ts` both read it, so
  a change to one implementation fails the other's suite. The web test runs in Vitest's
  `node` environment, because under jsdom `import.meta.url` is not a `file:` URL. It sits
  under `lib/format/**`, which has the 100% coverage gate.
- **Combobox** is React Aria's `ComboBox` with
  `defaultFilter={matchesLookup}` ("mercedes benz" finds "Mercedes-Benz"; React Aria's
  default filter already ignores accents, but not spaces or hyphens).
  `allowsEmptyCollection` keeps the list open to show "No matches" (a `role="status"`
  message). `isLoading` adds a spinner and "Loading…". The hint and error use React Aria's
  `description`/`errorMessage` slots, so they are wired into `aria-describedby`. The
  popover sits on the `z-modal` layer, because it can open inside a sheet or modal; as a
  later portal it paints above the dialog that opened it. The gallery's Filters sheet now
  includes it.
- **Design amendment A17: RangeSlider uses React Aria hooks, not its `Slider` component.**
  The component builds `aria-valuetext` from an `Intl.NumberFormat`, so a value in pence
  would be read as "500,000", not "£5,000", against design §10's rule that every value
  goes through `lib/format`. It also pages by a tenth of the range, not a fixed number of
  steps. `useSliderState` takes the formatter as an object: a subclass of
  `Intl.NumberFormat` whose `format` calls the caller's `formatValue`. The state is spread
  with `pageSize: step * PAGE_STEPS` (10). `react-aria` 3.52.1 and `react-stately` 3.50.0
  are now direct dependencies, pinned to the versions `react-aria-components` 1.21.1
  already resolves (deduplicated, no extra copy).
- RangeSlider details: the track is 44px tall (the whole track is a touch target) with a
  4px bar. The thumbs are 24px and carry `data-slider-thumb`. The gallery's 24px target
  check now measures thumbs instead of the 1px visually hidden range inputs. Thumb and fill
  positions are style attributes, allowed by A2. `onChangeEnd` fires once per key press or
  drag, which is where 3.10/Feature 07 will update the URL.
- Bundle: `/` unchanged at **111.6 kB**. The gallery is 157.6 → 189.4 kB (+31.8 kB for
  ComboBox, ListBox, Popover and the slider hooks); it is not gated.
- Tests: 25 lookup tests and 11 widget tests.
  - Combobox: keyboard-only selection; `aria-expanded`, `aria-controls` and
    `aria-activedescendant` while focus stays in the input; normal-form filtering;
    empty and loading messages; hint and error descriptions.
  - Performance: the 546 seed models from `models.csv`, padded to 550, are filtered by
    one keystroke within a 1 s bound under jsdom.
  - Slider: "£5,000" from 500,000 pence; arrows, `PageUp`/`PageDown` = 10 steps,
    `Home`, and `onChangeEnd`; thumbs cannot cross (`End` stops at the other thumb, and
    its `max` attribute is the other thumb's value); mileage reads "60,000 miles";
    `renderToString` positions thumbs with `style="left:…"` and emits no `<style>`.
  - The price test uses a £100k range, so a tenth of the range (20 steps) differs from
    10 steps. With a £50k range the two coincide and the test proved nothing.
  - e2e: the make combobox in a real browser and the price slider by keyboard (the thumb
    really moves), both with the CSP fixture watching.
- Guard probes: removing the `pageSize` override fails the key test; removing
  `defaultFilter` fails the normal-form test.
- Local e2e: 17 of 18 pass. `foundation.spec.ts` still fails locally only because Docker
  is down.
- Housekeeping: Prettier reformatted five 3.7 files edited after 3.7's last full
  pre-commit run (the toast split). The `feature3` push of 3.7 may show a red pre-commit
  job; this commit fixes it.

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

**Notes (done 2026-10-21, branch `feature3`)**
- `components/ui/states.tsx` (hook-free, renders on the server): `EmptyState`, `ErrorState`,
  `PermissionDenied` and `NotFound`. `ErrorState`'s variant follows from `ui.kind`:
  - `generic`: retry, plus the request id shown small.
  - `unavailable`: the caller's `continueAction` comes first, with a secondary retry.
  - `offline`.

  Copy always comes from `problem-ui.ts`; callers pass only actions. Each root carries
  `data-problem-kind`. `problem-ui.ts` now exports `SIGN_IN_UI` and `PERMISSION_UI`.
- `ProblemView` (client) maps `problemUi(error).kind` to one of them. `sign-in` takes a
  `signInAction` (Feature 04 supplies it). `field-errors`/`conflict` fall back to a plain
  error without retry until `useApiForm` (3.10) handles them.
- **Bug found by the code table test:** `PermissionDenied` and `NotFound` used their
  default copy, so `dealer_not_approved` showed "You do not have access" instead of
  "Awaiting approval". `ProblemView` now passes the resolved UI through.
- `useRetryAfter(seconds, resetKey)` (`lib/hooks/use-retry-after.ts`):
  - It counts from a deadline, so a throttled background tab still ends on time.
  - `resetKey` (the error object) restarts the wait for a new 429 with the same seconds.
  - The live region starts empty. The start message is set on the next task (also
    satisfying oxlint's `set-state-in-effect` rule), then "You can try again now." at
    zero: two announcements in total.
  - `RateLimitNotice` shows `formatCountdown` ("0:15") outside the live region.
  - New `lib/format` helpers `formatCountdown` and `formatWait` ("45 seconds",
    "3 minutes"), under the 100% gate.
- Offline:
  - `lib/api/connectivity.ts` is a browser-only signal. `requestApi` reports an
    `ApiNetworkError` as a failure and any response, even a 500, as a success. Timeouts
    and caller aborts count as neither.
  - Reports made on the server are ignored, because module state there is shared by
    every visitor.
  - `OfflineBanner` combines `navigator.onLine` with that signal through
    `useSyncExternalStore`. Its live region is always present and the server renders it
    empty. The `online` event clears a recorded failure.
  - It is mounted once in `Providers`, eagerly, since it must work when the network does
    not. 3.11 may move it into the layouts.
- Bundle: `/` is **113.5 kB** (+1.9 kB for the banner and signal). The gallery is
  194.7 kB, not gated.
- Tests: 38 state tests.
  - A `Record<ProblemUiKind, error>` table, so a new kind fails typecheck until it is
    tested.
  - Every `ProblemCode` renders its title.
  - `integration_unavailable` shows "continue manually" before retry.
  - The request id is shown; there is no retry where it cannot help; the 401 action.
  - Countdown under fake timers: disabled, then enabled at zero, with exactly two
    announcements, and a restart on a new error.
  - Offline: events, a network error while `onLine` is true, recovery, empty SSR.
  - Signal tests in `connectivity.test.ts` and `response.test.ts`.
  - e2e: Playwright `setOffline` toggles the banner, simulated failure and success, the
    countdown under `page.clock`, and the unavailable variant.
- Guard probes: announcing every tick fails the countdown test; ignoring the network
  signal fails the "`onLine` still true" test.
- **Flaky combobox spec, fixed.** About one run in ten, the list closed right after typing.
  Next scrolls to a hash target after hydration, and React Aria closes an open popover
  on scroll. The spec now opens `/dev/components` without a hash and scrolls the control
  into view (15 of 15 repeats pass). Also added `gotoHydrated()` in `e2e/fixtures.ts`:
  `Providers` sets `<html data-hydrated>` in an effect, and specs that type or press keys
  wait for it.
- **Pre-commit lesson:** `pre-commit run --all-files` only checks *tracked* files, so new
  files from 3.7 and 3.8 were never formatted. Prettier fixed four 3.8 files here (format
  only). The `feature3` pushes of 3.7 and 3.8 may show a red pre-commit job. From now on:
  `git add -A`, then pre-commit, then commit.
- Local e2e: 20 of 21 pass. `foundation.spec.ts` still fails locally only because Docker
  is down.

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

**Notes (built 2026-10-22, branch `feature3`; Redis-backed tests run only in CI)**
- **Backend probe** (`app/api/v1/endpoints/dev.py`, dev router, `ENVIRONMENT=local`
  only):
  - `GET /dev/form-probe/{id}` seeds and returns a record held in Redis per probe id, so
    parallel tests never share one.
  - `POST /dev/form-probe/{id}`:
    - validates the body (422 `errors[]` as `body.<field>`);
    - name "Taken" gives a server-side 422 that includes `body.dealer_id`, a field the
      form does not have;
    - checks `updated_at` through the real `ensure_not_stale` (409 with `current`);
    - `mode` can ask for a 503 `integration_unavailable`, a 429 with `Retry-After: 3`,
      or a 15 s hang;
    - counts how often it really ran, per `Idempotency-Key`.
  - `POST …/touch` plays "someone else saved". `GET …/executions` returns the counts.
  - It runs behind the real `IdempotencyMiddleware`.
  - Tests in `tests/test_dev_routes.py`: absent in staging and production, save/stale
    and re-apply, touch, schema 422, unknown-field 422, 503/429, hang (with
    `HANG_SECONDS` patched to 0), one execution per key with a replay header, and id
    validation.
- **e2e had no route from the browser to the API.** Deployed environments have nginx in
  front of `/api/`; Playwright and `next dev` do not. `app/api/v1/[...path]/route.ts` →
  `lib/api/dev-proxy.ts` forwards the API client's headers and answers, but only with
  `DEV_API_PROXY=1` at runtime (set in `playwright.config.ts`); otherwise it is a 404
  without calling out. Tests in `lib/api/dev-proxy.test.ts`.
- **Web:**
  - `lib/forms/` holds four pure modules (key lifecycle per A18, `apiFieldErrors` /
    `schemaFieldErrors`, `conflictChanges`, `IDEMPOTENT_ENDPOINTS`) and the
    `useApiForm` hook.
  - The submit lock is a ref; failures keep the values.
  - A 422 goes onto fields; unknown fields become `formErrors`.
  - A 409 with `current` becomes `conflict`: `reloadTheirs`, or `reapplyMine`, which
    resubmits on `tokenField`.
  - Anything else becomes `problem`, for `ProblemView`.
  - `useApiForm` sends a key only when given an `IDEMPOTENT_ENDPOINTS` name.
  - zod 4.6.5 is pinned (4.6.6 was under two weeks old).
- `ConflictDialog` is a non-dismissable `Modal` (now with controlled `isOpen` and
  `onOpenChange`). It shows a Field / Yours / Theirs table built from the labelled
  fields, with "Reload theirs" and "Re-apply mine".
- Gallery: `#form-probe` drives every path. Open it with `?probe=<id>` to pick the record.
- Tests: 24 unit tests in `lib/forms`, held to a new 100% gate in `vitest.config.mts`.
  - The double submit is two `handleSubmit` calls in one `act` → one request.
  - Network-error and timeout retries reuse the key; 422, 409 and success spend it.
  - Re-apply carries their token; the default key is a UUID; and more.
  - Probes: always reusing the key fails 5 tests; spending it on a network error fails 2.
- e2e `form-probe.spec.ts` (real API):
  - a double-click → one POST and one execution;
  - a response lost at the network level (`route.fetch()` then `abort`) → retry sends
    the same key and the probe runs once;
  - 422 on the field plus the form-level alert;
  - 409 dialog → "Re-apply mine" saves;
  - the 429 countdown;
  - 503 "continue manually";
  - a hang shows the timeout state after ≥ 9.5 s.
- **Local status:** 20 of 28 e2e pass. The 7 probe specs and `foundation.spec.ts` fail
  locally only because Docker's Redis accepts connections but never answers. The probe
  section showed the API's own 500 with its request id, which proves the proxy path
  works. CI runs them for real; 3.10 is Done once that run is green.
- Bundle: `/` is 114.0 kB. The gallery is 288.6 kB (zod non-JIT; see A19).

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
