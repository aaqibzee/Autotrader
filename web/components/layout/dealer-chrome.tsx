import { BRAND } from "@/lib/brand";
import Link from "next/link";
import type { ReactNode } from "react";
import { cx } from "@/components/ui/cx";
import { DealerNav } from "./dealer-nav";
import { SHELL_ROUTES } from "./routes";
import { SkipLink } from "./skip-link";

/**
 * Dealer portal chrome (Feature 03 §5). The dealer's name and approval status come from
 * Feature 04's dealer context (A8); until then they are absent and no banner shows.
 */
export type DealerStatus = "pending" | "approved" | "suspended";

const BANNER: Partial<Record<DealerStatus, { tone: string; text: string }>> = {
  pending: {
    tone: "border-warning bg-warning-tint text-warning",
    text: "Awaiting approval: you can create drafts but not publish.",
  },
  suspended: {
    tone: "border-danger bg-danger-tint text-danger",
    text: "Your dealership is suspended, so your listings are hidden. Contact support.",
  },
};

export function DealerChrome({
  children,
  dealerName,
  dealerStatus,
}: {
  children: ReactNode;
  dealerName?: string;
  dealerStatus?: DealerStatus;
}) {
  const banner = dealerStatus ? BANNER[dealerStatus] : undefined;
  return (
    <div className="flex min-h-dvh flex-col">
      <SkipLink />
      <header className="sticky top-0 z-header border-b border-line bg-surface">
        <div className="flex min-h-14 items-center justify-between gap-4 px-4">
          <Link
            className="inline-flex min-h-11 items-center font-black tracking-tight"
            href={SHELL_ROUTES.home}
          >
            {BRAND.wordmark}
            <span className="text-brand">.</span>
            <span className="ml-2 text-sm font-semibold text-ink-muted">
              Dealer
            </span>
          </Link>
          {dealerName ? (
            <p className="truncate text-sm font-semibold text-ink">
              {dealerName}
            </p>
          ) : null}
        </div>
        {banner ? (
          <p
            className={cx(
              "border-t px-4 py-2 text-sm font-medium",
              banner.tone,
            )}
            data-dealer-banner={dealerStatus}
          >
            {banner.text}
          </p>
        ) : null}
      </header>
      <div className="flex flex-1">
        <DealerNav />
        {/* Bottom padding clears the bottom nav on phones. */}
        <main className="min-w-0 flex-1 pb-20 lg:pb-0" id="main" tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  );
}
