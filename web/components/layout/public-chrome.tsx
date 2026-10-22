import { BRAND } from "@/lib/brand";
import Link from "next/link";
import type { ReactNode } from "react";
import { AccountIsland } from "./account-island";
import { SHELL_ROUTES } from "./routes";
import { SkipLink } from "./skip-link";

/**
 * Public chrome (Feature 03 §5): skip link, header, `<main id="main">`, footer.
 * Server-rendered and the same for every visitor, so public pages can be cached; the only
 * personal part is the account slot, a client island. Mobile-first: the header wraps
 * onto two rows below `md`, and nothing scrolls sideways at 320 px.
 *
 * What the shell cannot know yet arrives as props (A8):
 * - `showValuation`: Feature 12's flag; there is no public flags endpoint yet.
 * - `account`: the slot; defaults to the signed-out island until Feature 04.
 * - `makeLinks`: footer links by make, from Feature 13.
 */
export function PublicChrome({
  children,
  showValuation = false,
  account = <AccountIsland />,
  makeLinks,
}: {
  children: ReactNode;
  showValuation?: boolean;
  account?: ReactNode;
  makeLinks?: ReactNode;
}) {
  return (
    <div className="flex min-h-dvh flex-col">
      <SkipLink />
      <PublicHeader account={account} showValuation={showValuation} />
      <main className="flex-1" id="main" tabIndex={-1}>
        {children}
      </main>
      <PublicFooter makeLinks={makeLinks} />
    </div>
  );
}

const navLink =
  "inline-flex min-h-11 items-center rounded-md px-2 text-sm font-semibold text-ink-soft hover-state:bg-sunken hover-state:text-ink";

function PublicHeader({
  account,
  showValuation,
}: {
  account: ReactNode;
  showValuation: boolean;
}) {
  return (
    <header className="sticky top-0 z-header border-b border-line bg-surface">
      <div className="shell flex flex-wrap items-center gap-x-4 gap-y-1 py-1 md:flex-nowrap">
        <Link
          aria-label={`${BRAND.name} home`}
          className="inline-flex min-h-11 items-center text-lg font-black tracking-tight"
          href={SHELL_ROUTES.home}
        >
          {BRAND.wordmark}
          <span className="text-brand">.</span>
        </Link>
        <div className="order-last flex w-full items-center md:order-none md:w-auto md:flex-1">
          <Link
            className="inline-flex min-h-11 flex-1 items-center gap-2 rounded-full border border-border-strong px-4 text-sm text-ink-muted hover-state:border-ink md:max-w-sm"
            href={SHELL_ROUTES.search}
          >
            <svg
              aria-hidden="true"
              className="size-4 shrink-0"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              viewBox="0 0 24 24"
            >
              <path d="M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zm5-2 4 4" />
            </svg>
            Search cars
          </Link>
        </div>
        <nav aria-label="Main" className="ml-auto flex items-center gap-1">
          {showValuation ? (
            <Link className={navLink} href={SHELL_ROUTES.valuation}>
              Value my car
            </Link>
          ) : null}
          <Link className={navLink} href={SHELL_ROUTES.forDealers}>
            For dealers
          </Link>
        </nav>
        {account}
      </div>
    </header>
  );
}

const footerLink =
  "inline-flex min-h-11 items-center underline-offset-4 hover-state:underline";

function PublicFooter({ makeLinks }: { makeLinks?: ReactNode }) {
  return (
    <footer className="mt-16 border-t border-line bg-canvas">
      <div className="shell grid gap-8 py-10">
        {makeLinks ? (
          <nav aria-label="Cars by make" className="text-sm">
            {makeLinks}
          </nav>
        ) : null}
        <div className="flex flex-wrap items-center justify-between gap-4 text-sm text-ink-muted">
          <p>
            © {BRAND.name}. {BRAND.description}
          </p>
          <nav aria-label="Legal">
            <ul className="flex flex-wrap gap-x-4">
              <li>
                <Link className={footerLink} href={SHELL_ROUTES.terms}>
                  Terms
                </Link>
              </li>
              <li>
                <Link className={footerLink} href={SHELL_ROUTES.privacy}>
                  Privacy
                </Link>
              </li>
              <li>
                <Link className={footerLink} href={SHELL_ROUTES.cookies}>
                  Cookies
                </Link>
              </li>
            </ul>
          </nav>
        </div>
      </div>
    </footer>
  );
}
