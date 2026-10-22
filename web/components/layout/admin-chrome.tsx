import { BRAND } from "@/lib/brand";
import type { ReactNode } from "react";
import { SkipLink } from "./skip-link";

/** Admin chrome (Feature 03 §5): deliberately minimal; Feature 14 fills it in. */
export function AdminChrome({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col">
      <SkipLink />
      <header className="border-b border-line bg-ink text-surface">
        <div className="shell flex min-h-14 items-center font-black tracking-tight">
          {BRAND.wordmark}
          <span className="ml-2 text-sm font-semibold">Admin</span>
        </div>
      </header>
      <main className="shell flex-1 py-8" id="main" tabIndex={-1}>
        {children}
      </main>
    </div>
  );
}
