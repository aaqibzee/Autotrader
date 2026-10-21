import type { Route } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import { cx } from "./cx";

export type PageItem = number | "gap";

/**
 * The page numbers to show: first, last, and `siblings` either side of `current`, with
 * "gap" for each run that is skipped. A gap never stands for a single page: that page is
 * shown instead, so the control is never wider for no saving.
 */
export function pageItems(current: number, total: number, siblings = 1): PageItem[] {
  if (total <= 0) return [];
  const page = Math.min(Math.max(current, 1), total);
  const shown = new Set([1, total]);
  for (let p = page - siblings; p <= page + siblings; p += 1) {
    if (p >= 1 && p <= total) shown.add(p);
  }
  const sorted = [...shown].sort((a, b) => a - b);
  const items: PageItem[] = [];
  sorted.forEach((p, i) => {
    const previous = sorted[i - 1];
    if (previous !== undefined) {
      if (p - previous === 2) items.push(previous + 1);
      else if (p - previous > 2) items.push("gap");
    }
    items.push(p);
  });
  return items;
}

const pageLink =
  "inline-flex min-h-11 min-w-11 items-center justify-center rounded-md px-3 text-sm font-semibold figures";

export type PaginationProps = {
  current: number;
  total: number;
  /** Plain links, not buttons: every results page has its own URL (Feature 07). */
  hrefFor: (page: number) => string;
  className?: string;
};

export function Pagination({ current, total, hrefFor, className }: PaginationProps) {
  if (total <= 1) return null;
  const page = Math.min(Math.max(current, 1), total);
  return (
    <nav aria-label="Pagination" className={className}>
      <ul className="flex flex-wrap items-center gap-1">
        <li>
          {page > 1 ? (
            <Link className={cx(pageLink, "text-brand-strong hover-state:bg-brand-tint")} href={hrefFor(page - 1) as Route} rel="prev">
              Previous
            </Link>
          ) : (
            <span aria-disabled="true" className={cx(pageLink, "text-ink-muted")}>
              Previous
            </span>
          )}
        </li>
        {pageItems(page, total).map((item, index) =>
          item === "gap" ? (
            <li aria-hidden="true" className={cx(pageLink, "text-ink-muted")} key={`gap-${index}`}>
              …
            </li>
          ) : (
            <li key={item}>
              <Link
                aria-current={item === page ? "page" : undefined}
                aria-label={`Page ${item}`}
                className={cx(
                  pageLink,
                  item === page ? "bg-ink text-surface" : "text-brand-strong hover-state:bg-brand-tint",
                )}
                href={hrefFor(item) as Route}
              >
                {item}
              </Link>
            </li>
          ),
        )}
        <li>
          {page < total ? (
            <Link className={cx(pageLink, "text-brand-strong hover-state:bg-brand-tint")} href={hrefFor(page + 1) as Route} rel="next">
              Next
            </Link>
          ) : (
            <span aria-disabled="true" className={cx(pageLink, "text-ink-muted")}>
              Next
            </span>
          )}
        </li>
      </ul>
    </nav>
  );
}

export type Crumb = { label: ReactNode; href?: string };

/** The last crumb is the current page: not a link, marked `aria-current`. */
export function Breadcrumbs({ items, className }: { items: readonly Crumb[]; className?: string }) {
  if (items.length === 0) return null;
  return (
    <nav aria-label="Breadcrumb" className={className}>
      <ol className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
        {items.map((crumb, index) => {
          const last = index === items.length - 1;
          return (
            <li className="flex items-center gap-2" key={index}>
              {last || !crumb.href ? (
                <span aria-current={last ? "page" : undefined} className={last ? "text-ink" : "text-ink-muted"}>
                  {crumb.label}
                </span>
              ) : (
                <Link className="inline-flex min-h-6 items-center text-brand-strong underline-offset-2 hover-state:underline" href={crumb.href as Route}>
                  {crumb.label}
                </Link>
              )}
              {!last && (
                <span aria-hidden="true" className="text-ink-muted">
                  /
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
