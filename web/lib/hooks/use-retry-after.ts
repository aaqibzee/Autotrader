"use client";

import { formatWait } from "@/lib/format";
import { useEffect, useState } from "react";

/**
 * Countdown for a 429's `Retry-After` (Feature 03 §3). A rate limit is shown inline with
 * this countdown, never as a toast.
 *
 * `announcement` is for one polite live region. It changes exactly twice: when the wait
 * starts ("You can try again in 30 seconds.") and when it ends ("You can try again
 * now."). A screen reader reading every tick would be unusable. It starts empty and is
 * filled just after mount, because a live region that arrives already filled is often not read.
 *
 * `resetKey` restarts the countdown for a new error carrying the same number of seconds.
 */
export type RetryAfter = {
  /** Whole seconds left. */
  remaining: number;
  ready: boolean;
  announcement: string;
};

export const READY_ANNOUNCEMENT = "You can try again now.";

export function useRetryAfter(
  seconds: number | undefined,
  resetKey?: unknown,
): RetryAfter {
  const total = Math.max(0, Math.ceil(seconds ?? 0));
  const [run, setRun] = useState({
    total,
    resetKey,
    remaining: total,
    announcement: "",
  });

  // A new wait replaces the old one during render, so no frame shows the stale count.
  if (run.total !== total || run.resetKey !== resetKey) {
    setRun({ total, resetKey, remaining: total, announcement: "" });
  }

  useEffect(() => {
    if (total === 0) return;
    // On the next task, once the empty live region is in the accessibility tree.
    const start = setTimeout(() => {
      setRun((current) => ({
        ...current,
        announcement: `You can try again in ${formatWait(total)}.`,
      }));
    }, 0);
    // Counted from a deadline, not by decrementing, so a throttled background tab still
    // reaches zero on time.
    const deadline = Date.now() + total * 1_000;
    const timer = setInterval(() => {
      const remaining = Math.max(0, Math.ceil((deadline - Date.now()) / 1_000));
      setRun((current) => ({
        ...current,
        remaining,
        announcement:
          remaining === 0 ? READY_ANNOUNCEMENT : current.announcement,
      }));
      if (remaining === 0) clearInterval(timer);
    }, 1_000);
    return () => {
      clearTimeout(start);
      clearInterval(timer);
    };
  }, [total, resetKey]);

  return {
    remaining: run.remaining,
    ready: run.remaining === 0,
    announcement: run.announcement,
  };
}
