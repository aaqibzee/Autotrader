"use client";

import {
  isNetworkFailing,
  reportNetworkSuccess,
  subscribeNetworkFailure,
} from "@/lib/api/connectivity";
import { OFFLINE_UI } from "@/lib/api/problem-ui";
import { useEffect, useSyncExternalStore } from "react";

function subscribeOnline(listener: () => void) {
  window.addEventListener("online", listener);
  window.addEventListener("offline", listener);
  return () => {
    window.removeEventListener("online", listener);
    window.removeEventListener("offline", listener);
  };
}

/**
 * "You appear to be offline" across the top of the page (Feature 03 §3). Shown when the
 * device reports no network, or when our last request got no response even though it
 * says it has one (`lib/api/connectivity.ts`). One instance, mounted in the root providers.
 *
 * The live region is always in the DOM and only its content changes, so the banner is
 * announced when it appears. The server renders it empty: it cannot know.
 */
export function OfflineBanner() {
  const online = useSyncExternalStore(
    subscribeOnline,
    () => navigator.onLine,
    () => true,
  );
  const failing = useSyncExternalStore(
    subscribeNetworkFailure,
    isNetworkFailing,
    () => false,
  );

  // Coming back online starts afresh; the next request decides again.
  useEffect(() => {
    window.addEventListener("online", reportNetworkSuccess);
    return () => window.removeEventListener("online", reportNetworkSuccess);
  }, []);

  const show = !online || failing;
  return (
    <div aria-live="polite" data-offline-banner="" role="status">
      {show ? (
        <p className="border-b border-info bg-info-tint px-4 py-2 text-center text-sm text-info">
          <strong className="font-semibold">{OFFLINE_UI.title}.</strong>{" "}
          {OFFLINE_UI.message}
        </p>
      ) : null}
    </div>
  );
}
