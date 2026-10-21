
import { UNSTABLE_ToastQueue as AriaToastQueue } from "react-aria-components";

/**
 * The one global toast system (Feature 03 §2): success and failure notices that are not
 * tied to a field. React Aria's toast API is still `UNSTABLE_` (pinned 1.21.1), so it is
 * used only here and in toast-region.tsx; an API change touches nothing else.
 *
 * The queue is tiny and can be imported anywhere. The region that renders it is a
 * separate chunk, loaded after hydration (components/providers.tsx): toasts only follow
 * a user action, so the public shell does not pay for them up front.
 *
 * Not for errors with a recovery path: those go through `problemUi` to an inline state
 * (lib/api/problem-ui.ts). A 429 never becomes a toast (design §3).
 */
export type ToastTone = "info" | "success" | "error";
export type ToastContent = { message: string; tone: ToastTone };

/** No more than three on screen; the rest wait in order. */
export const MAX_VISIBLE_TOASTS = 3;
/** Info and success dismiss themselves. Errors stay until dismissed (WCAG 2.2.1 timing). */
export const TOAST_TIMEOUT_MS = 6_000;

export const toastQueue = new AriaToastQueue<ToastContent>({
  maxVisibleToasts: MAX_VISIBLE_TOASTS,
});

/**
 * Shows a toast, unless an identical one is already on screen: ten failures of the same
 * request show one message, not a stack (design §3, "never a toast storm").
 * Returns the toast key, or `undefined` when it was a duplicate.
 */
export function showToast(message: string, tone: ToastTone = "info"): string | undefined {
  const duplicate = toastQueue.visibleToasts.some(
    (toast) => toast.content.message === message && toast.content.tone === tone,
  );
  if (duplicate) return undefined;
  return toastQueue.add(
    { message, tone },
    { timeout: tone === "error" ? undefined : TOAST_TIMEOUT_MS },
  );
}

/** Hook-shaped access for components; the queue is global, so this needs no provider. */
export function useToast() {
  return { show: showToast };
}
