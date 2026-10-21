import { afterEach, describe, expect, it, vi } from "vitest";
import {
  isNetworkFailing,
  reportNetworkFailure,
  reportNetworkSuccess,
  subscribeNetworkFailure,
} from "./connectivity";

afterEach(() => {
  vi.unstubAllGlobals();
  reportNetworkSuccess();
});

describe("connectivity signal", () => {
  it("notifies subscribers on each change, not on repeats", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeNetworkFailure(listener);

    reportNetworkFailure();
    reportNetworkFailure();
    expect(isNetworkFailing()).toBe(true);
    expect(listener).toHaveBeenCalledTimes(1);

    reportNetworkSuccess();
    expect(isNetworkFailing()).toBe(false);
    expect(listener).toHaveBeenCalledTimes(2);

    unsubscribe();
    reportNetworkFailure();
    expect(listener).toHaveBeenCalledTimes(2);
  });

  it("ignores reports made on the server, where the state would be shared by every visitor", () => {
    vi.stubGlobal("window", undefined);
    reportNetworkFailure();
    expect(isNetworkFailing()).toBe(false);
  });
});
