"use client";

import { OfflineBanner } from "@/components/ui/offline-banner";
import type { Route } from "next";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { type ReactNode, useEffect } from "react";
import { I18nProvider, RouterProvider } from "react-aria-components";

// Toasts only ever follow a user action, so the region loads after hydration instead of
// riding in every public page's first load. Toasts raised before it mounts wait in the
// queue and appear when it does.
const ToastRegion = dynamic(
  () =>
    import("@/components/ui/toast-region").then((module) => module.ToastRegion),
  {
    ssr: false,
  },
);

/**
 * App-wide client context, mounted once in the root layout (Feature 03 slice 3.7).
 *
 * - `I18nProvider locale="en-GB"`: React Aria formats numbers and dates for the locale it
 *   is given. Without it the server uses its own default and the browser uses the
 *   visitor's language, so a slider label rendered "£5,000" on the server could hydrate
 *   as "5.000 £", a hydration mismatch. en-GB only (design §10).
 * - `RouterProvider`: React Aria links navigate client-side through Next's router.
 * - The single toast region, lazily loaded.
 * - The single offline banner (slice 3.9). Eager: it must work when the network does not.
 */
export function Providers({ children }: { children: ReactNode }) {
  const router = useRouter();
  // `<html data-hydrated>` once React owns the page. e2e waits for it before typing,
  // because keys pressed into server-rendered markup before hydration are lost (3.9).
  useEffect(() => {
    document.documentElement.dataset.hydrated = "";
  }, []);
  return (
    <I18nProvider locale="en-GB">
      <RouterProvider navigate={(href) => router.push(href as Route)}>
        <OfflineBanner />
        {children}
        <ToastRegion />
      </RouterProvider>
    </I18nProvider>
  );
}
