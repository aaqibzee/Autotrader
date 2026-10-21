/**
 * Loads the Sentry browser SDK after the page is idle instead of in the first-load
 * bundle (Feature 03 A1: the SDK is most of the shell's JS budget).
 *
 * Errors thrown before the SDK arrives are not lost. A small queue listens for `error`
 * and `unhandledrejection` until the SDK is ready, then hands them over and removes its
 * listeners (the SDK installs its own global handlers on init, so keeping ours would
 * report everything twice). The first queued error also triggers the load immediately,
 * rather than waiting for idle.
 */
export type SentryModule = {
  init: (options: never) => unknown;
  captureException: (error: unknown) => unknown;
  captureRouterTransitionStart: (href: string, navigationType: string) => void;
};

export type LazySentryOptions = {
  dsn: string | undefined;
  /** `() => import("@sentry/nextjs")`; injected so tests need no SDK. */
  load: () => Promise<SentryModule>;
  /** Builds the `init` options from the DSN (lib/observability/sentry-options.ts). */
  options: (dsn: string) => unknown;
  target: Pick<Window, "addEventListener" | "removeEventListener">;
  /** Runs the callback when the browser is idle. */
  whenIdle: (callback: () => void) => void;
};

export type LazySentry = {
  onRouterTransitionStart: (href: string, navigationType: string) => void;
  /** Resolves once the SDK is initialised (or immediately, with no DSN). For tests. */
  ready: Promise<void>;
};

/** Enough to cover a burst at start-up without holding a page's worth of errors. */
export const MAX_QUEUED_ERRORS = 20;

export function startLazySentry(options: LazySentryOptions): LazySentry {
  const { dsn, target } = options;
  // No DSN means Sentry is disabled (local, CI): never download the SDK at all.
  if (!dsn) return { onRouterTransitionStart: () => {}, ready: Promise.resolve() };

  const queued: unknown[] = [];
  let sdk: SentryModule | undefined;
  let loading: Promise<void> | undefined;

  const onError = (event: Event) => {
    const error = "error" in event ? (event as ErrorEvent).error : undefined;
    const reason = "reason" in event ? (event as PromiseRejectionEvent).reason : undefined;
    if (queued.length < MAX_QUEUED_ERRORS) queued.push(error ?? reason ?? event);
    void load();
  };

  function load(): Promise<void> {
    loading ??= options
      .load()
      .then((module) => {
        module.init(options.options(dsn!) as never);
        target.removeEventListener("error", onError);
        target.removeEventListener("unhandledrejection", onError);
        for (const error of queued.splice(0)) module.captureException(error);
        sdk = module;
      })
      .catch(() => {
        // The SDK failed to download (offline, blocked). Error reporting is best effort;
        // the page must not break because of it. Keep queuing, but stop listening.
        target.removeEventListener("error", onError);
        target.removeEventListener("unhandledrejection", onError);
      });
    return loading;
  }

  target.addEventListener("error", onError);
  target.addEventListener("unhandledrejection", onError);

  let resolveReady: () => void;
  const ready = new Promise<void>((resolve) => {
    resolveReady = resolve;
  });
  options.whenIdle(() => {
    void load().then(() => resolveReady());
  });

  return {
    // Navigations before the SDK loads are not traced; the first page load is measured
    // by the SDK's own browser tracing once it starts.
    onRouterTransitionStart: (href, navigationType) =>
      sdk?.captureRouterTransitionStart(href, navigationType),
    ready,
  };
}

/** `requestIdleCallback` where available (not Safari), else a short timeout. */
export function whenBrowserIdle(callback: () => void): void {
  if (typeof window.requestIdleCallback === "function") {
    window.requestIdleCallback(callback, { timeout: 5_000 });
  } else {
    window.setTimeout(callback, 2_000);
  }
}
