"use client";

import {
  Button as AriaButton,
  UNSTABLE_Toast as AriaToast,
  UNSTABLE_ToastContent as AriaToastContent,
  UNSTABLE_ToastRegion as AriaToastRegion,
} from "react-aria-components";
import { cx } from "./cx";
import { type ToastTone, toastQueue } from "./toast";

const TONES: Record<ToastTone, string> = {
  info: "border-info bg-info-tint text-info",
  success: "border-success bg-success-tint text-success",
  error: "border-danger bg-danger-tint text-danger",
};

/** Mounted once, in the root providers. */
export function ToastRegion() {
  return (
    <AriaToastRegion
      aria-label="Notifications"
      className="fixed right-4 bottom-4 left-4 z-toast flex flex-col items-stretch gap-2 outline-none sm:left-auto sm:w-96"
      queue={toastQueue}
    >
      {({ toast }) => (
        <AriaToast
          className={cx(
            "flex items-start gap-3 rounded-md border-l-4 p-4 shadow-overlay",
            TONES[toast.content.tone],
          )}
          toast={toast}
        >
          {/*
           * React Aria announces every toast assertively (role="alert"). Only errors should
           * interrupt; info and success are polite (role="status"), Feature 03 §8.
           */}
          <AriaToastContent
            aria-live={toast.content.tone === "error" ? "assertive" : "polite"}
            className="flex-1 text-sm font-medium"
            role={toast.content.tone === "error" ? "alert" : "status"}
          >
            {toast.content.message}
          </AriaToastContent>
          <AriaButton
            aria-label="Dismiss notification"
            className="-m-2 inline-flex size-11 shrink-0 items-center justify-center rounded-md hover-state:bg-surface"
            slot="close"
          >
            <svg aria-hidden="true" className="size-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </AriaButton>
        </AriaToast>
      )}
    </AriaToastRegion>
  );
}
