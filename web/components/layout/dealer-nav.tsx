"use client";

import { cx } from "@/components/ui/cx";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { SHELL_ROUTES } from "./routes";

/** The dealer portal's four sections (Feature 03 §5). */
const ITEMS = [
  {
    href: SHELL_ROUTES.dealerStock,
    label: "Stock",
    icon: <path d="M3 13h18l-2-6H5l-2 6zm0 0v5h18v-5M7 16h.01M17 16h.01" />,
  },
  {
    href: SHELL_ROUTES.dealerLeads,
    label: "Leads",
    icon: <path d="M4 5h16v11H8l-4 4V5z" />,
  },
  {
    href: SHELL_ROUTES.dealerTeam,
    label: "Team",
    icon: (
      <path d="M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm-7 10a7 7 0 0 1 14 0M17 3a4 4 0 0 1 0 8m3 10a7 7 0 0 0-3-5.7" />
    ),
  },
  {
    href: SHELL_ROUTES.dealerSettings,
    label: "Settings",
    icon: (
      <path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM4 12h2m12 0h2M12 4v2m0 12v2M6.3 6.3l1.4 1.4m8.6 8.6 1.4 1.4m0-11.4-1.4 1.4m-8.6 8.6-1.4 1.4" />
    ),
  },
] as const;

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      aria-hidden="true"
      className="size-5 shrink-0"
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="2"
      viewBox="0 0 24 24"
    >
      {children}
    </svg>
  );
}

/**
 * Side nav from `lg`, a fixed bottom bar below it, within a thumb's reach on a phone.
 * Client-only so it can mark the current section with `aria-current="page"`.
 */
export function DealerNav() {
  const pathname = usePathname();
  const isCurrent = (href: string) =>
    pathname === href || pathname.startsWith(`${href}/`);
  return (
    <>
      <nav
        aria-label="Dealer"
        className="hidden w-56 shrink-0 border-r border-line bg-surface lg:block"
        data-dealer-nav="side"
      >
        <ul className="grid gap-1 p-3">
          {ITEMS.map((item) => (
            <li key={item.label}>
              <Link
                aria-current={isCurrent(item.href) ? "page" : undefined}
                className={cx(
                  "flex min-h-11 items-center gap-3 rounded-md px-3 text-sm font-semibold",
                  isCurrent(item.href)
                    ? "bg-brand-tint text-brand-strong"
                    : "text-ink-soft hover-state:bg-sunken hover-state:text-ink",
                )}
                href={item.href}
              >
                <Icon>{item.icon}</Icon>
                {item.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      <nav
        aria-label="Dealer"
        className="fixed inset-x-0 bottom-0 z-header border-t border-line bg-surface pb-[env(safe-area-inset-bottom)] lg:hidden"
        data-dealer-nav="bottom"
      >
        <ul className="grid grid-cols-4">
          {ITEMS.map((item) => (
            <li key={item.label}>
              <Link
                aria-current={isCurrent(item.href) ? "page" : undefined}
                className={cx(
                  "flex min-h-14 flex-col items-center justify-center gap-0.5 text-xs font-semibold",
                  isCurrent(item.href) ? "text-brand-strong" : "text-ink-muted",
                )}
                href={item.href}
              >
                <Icon>{item.icon}</Icon>
                {item.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </>
  );
}
