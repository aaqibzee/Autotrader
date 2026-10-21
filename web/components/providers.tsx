"use client";

import type { Route } from "next";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
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
 */
export function Providers({ children }: { children: ReactNode }) {
  const router = useRouter();
  return (
    <I18nProvider locale="en-GB">
      <RouterProvider navigate={(href) => router.push(href as Route)}>
        {children}
        <ToastRegion />
      </RouterProvider>
    </I18nProvider>
  );
}
