import { sentryOptions } from "@/lib/observability/sentry-options";
import { startLazySentry, whenBrowserIdle } from "@/lib/observability/lazy-sentry";

// The Sentry SDK (~59 kB gzipped, more than half the framework floor) is loaded after
// the page is idle, not in the first-load bundle (Feature 03 A1). Errors thrown before it
// arrives are queued and reported once it has.
const sentry = startLazySentry({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  load: () => import("@sentry/nextjs"),
  options: sentryOptions,
  target: window,
  whenIdle: whenBrowserIdle,
});

export const onRouterTransitionStart = sentry.onRouterTransitionStart;
