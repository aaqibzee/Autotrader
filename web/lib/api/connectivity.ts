/**
 * "Our last request got no response at all" as a browser-wide signal (Feature 03 §3).
 *
 * `navigator.onLine` only knows whether the device has a network. It stays true on
 * captive portals, dead Wi-Fi and when our API is unreachable, so the offline banner also
 * listens here: `requestApi` reports an `ApiNetworkError` as a failure, and any response
 * at all (even a 500) as a success, which clears it.
 *
 * Browser only. On the server this module's state would be shared by every visitor's
 * request, so reports made there are ignored.
 */
type Listener = () => void;

let failing = false;
const listeners = new Set<Listener>();

const inBrowser = () => typeof window !== "undefined";

function set(next: boolean) {
  if (!inBrowser() || failing === next) return;
  failing = next;
  for (const listener of listeners) listener();
}

export function reportNetworkFailure(): void {
  set(true);
}

export function reportNetworkSuccess(): void {
  set(false);
}

export function isNetworkFailing(): boolean {
  return failing;
}

/** `useSyncExternalStore`-shaped subscription. */
export function subscribeNetworkFailure(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
