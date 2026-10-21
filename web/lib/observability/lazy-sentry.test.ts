import { afterEach, describe, expect, it, vi } from "vitest";
import {
  MAX_QUEUED_ERRORS,
  startLazySentry,
  whenBrowserIdle,
  type SentryModule,
} from "./lazy-sentry";

// Sentry is a third-party SDK, so a stand-in module is allowed here (playbook §2).
function fakeSentry() {
  return {
    init: vi.fn(),
    captureException: vi.fn(),
    captureRouterTransitionStart: vi.fn(),
  } satisfies SentryModule;
}

const DSN = "https://key@ingest.example.test/1";

// An options object, not a default parameter: `setup(undefined)` must mean "no DSN".
function setup({ dsn }: { dsn: string | undefined } = { dsn: DSN }) {
  const sdk = fakeSentry();
  const target = new EventTarget() as unknown as Window;
  let idle: (() => void) | undefined;
  const load = vi.fn(() => Promise.resolve(sdk));
  const lazy = startLazySentry({
    dsn,
    load,
    options: (value) => ({ dsn: value }),
    target,
    whenIdle: (callback) => {
      idle = callback;
    },
  });
  return { sdk, target, load, lazy, runIdle: () => idle?.() };
}

function throwOn(target: Window, error: unknown) {
  const event = new Event("error") as Event & { error: unknown };
  Object.defineProperty(event, "error", { value: error });
  target.dispatchEvent(event);
}

function rejectOn(target: Window, reason: unknown) {
  const event = new Event("unhandledrejection") as Event & { reason: unknown };
  Object.defineProperty(event, "reason", { value: reason });
  target.dispatchEvent(event);
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("startLazySentry", () => {
  it.each([undefined, ""])(
    "never downloads the SDK without a DSN (%j)",
    async (dsn) => {
      const { load, lazy, runIdle, target } = setup({ dsn });
      runIdle();
      throwOn(target, new Error("no DSN"));
      await lazy.ready;
      await settle();
      expect(load).not.toHaveBeenCalled();
      expect(() => lazy.onRouterTransitionStart("/a", "push")).not.toThrow();
    },
  );

  it("loads on idle, not at start-up", async () => {
    const { sdk, load, lazy, runIdle } = setup();
    expect(load).not.toHaveBeenCalled();
    runIdle();
    await lazy.ready;
    expect(load).toHaveBeenCalledOnce();
    expect(sdk.init).toHaveBeenCalledWith({ dsn: DSN });
  });

  it("reports errors thrown before the SDK arrived, once, after init", async () => {
    const { sdk, target, load } = setup();
    const early = new Error("before load");
    throwOn(target, early);
    rejectOn(target, "rejected early");
    await settle();

    // The first error triggers the load without waiting for idle.
    expect(load).toHaveBeenCalledOnce();
    expect(sdk.captureException.mock.calls).toEqual([
      [early],
      ["rejected early"],
    ]);
    expect(sdk.init.mock.invocationCallOrder[0]).toBeLessThan(
      sdk.captureException.mock.invocationCallOrder[0]!,
    );
  });

  it("stops listening once the SDK owns error handling (no double reports)", async () => {
    const { sdk, target, lazy, runIdle } = setup();
    runIdle();
    await lazy.ready;
    throwOn(target, new Error("after load"));
    await settle();
    expect(sdk.captureException).not.toHaveBeenCalled();
  });

  it("caps the queue", async () => {
    const { sdk, target } = setup();
    for (let i = 0; i < MAX_QUEUED_ERRORS + 5; i += 1)
      throwOn(target, new Error(`e${i}`));
    await settle();
    expect(sdk.captureException).toHaveBeenCalledTimes(MAX_QUEUED_ERRORS);
  });

  it("falls back to the event when it carries no error or reason", async () => {
    const { sdk, target } = setup();
    const bare = new Event("error");
    target.dispatchEvent(bare);
    await settle();
    expect(sdk.captureException).toHaveBeenCalledWith(bare);
  });

  it("forwards router transitions only after init", async () => {
    const { sdk, lazy, runIdle } = setup();
    lazy.onRouterTransitionStart("/before", "push");
    runIdle();
    await lazy.ready;
    lazy.onRouterTransitionStart("/after", "replace");
    expect(sdk.captureRouterTransitionStart.mock.calls).toEqual([
      ["/after", "replace"],
    ]);
  });

  it("survives the SDK failing to download", async () => {
    const target = new EventTarget() as unknown as Window;
    const removeSpy = vi.spyOn(target, "removeEventListener");
    let idle: (() => void) | undefined;
    const lazy = startLazySentry({
      dsn: DSN,
      load: () => Promise.reject(new Error("blocked")),
      options: () => ({}),
      target,
      whenIdle: (callback) => {
        idle = callback;
      },
    });
    idle?.();
    await expect(lazy.ready).resolves.toBeUndefined();
    expect(removeSpy).toHaveBeenCalledWith("error", expect.any(Function));
    expect(() => lazy.onRouterTransitionStart("/x", "push")).not.toThrow();
  });
});

describe("whenBrowserIdle", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("uses requestIdleCallback when the browser has it", () => {
    const requestIdleCallback = vi.fn();
    vi.stubGlobal("requestIdleCallback", requestIdleCallback);
    const callback = () => {};
    whenBrowserIdle(callback);
    expect(requestIdleCallback).toHaveBeenCalledWith(callback, {
      timeout: 5_000,
    });
  });

  it("falls back to a timeout without it", () => {
    vi.useFakeTimers();
    vi.stubGlobal("requestIdleCallback", undefined);
    const callback = vi.fn();
    whenBrowserIdle(callback);
    vi.advanceTimersByTime(1_999);
    expect(callback).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(callback).toHaveBeenCalledOnce();
  });
});
