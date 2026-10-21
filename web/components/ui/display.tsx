import type { HTMLAttributes, ReactNode } from "react";
import { cx } from "./cx";

export function Card({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      {...rest}
      className={cx("rounded-lg border border-line bg-surface shadow-card", className)}
    />
  );
}

export type BadgeTone = "neutral" | "brand" | "success" | "warning" | "danger" | "info" | "inverse";

// Each pair is a checked text/background pairing in styles/pairings.ts.
const BADGE_TONES: Record<BadgeTone, string> = {
  neutral: "bg-sunken text-ink",
  brand: "bg-brand-tint text-brand-strong",
  success: "bg-success-tint text-success",
  warning: "bg-warning-tint text-warning",
  danger: "bg-danger-tint text-danger",
  info: "bg-info-tint text-info",
  inverse: "bg-ink text-surface",
};

export function Badge({
  tone = "neutral",
  className,
  children,
}: {
  tone?: BadgeTone;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-sm px-2 py-0.5 text-xs font-semibold whitespace-nowrap",
        BADGE_TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/** Listing status badges, worded once (Feature 03 §2). */
export const ListingBadges = {
  /** Demo stock (Feature 02 A1/A2): never for sale, always labelled. */
  Example: () => <Badge tone="info">Example listing</Badge>,
  Reserved: () => <Badge tone="warning">Reserved</Badge>,
  Sold: () => <Badge tone="inverse">Sold</Badge>,
};

/** A neutral label, e.g. a spec on a card ("Automatic", "ULEZ"). Static; filters own removable chips. */
export function Tag({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-sm border border-line bg-surface px-2 py-0.5 text-sm text-ink-soft",
        className,
      )}
    >
      {children}
    </span>
  );
}

/**
 * Placeholder block while content loads. Decorative to assistive technology: the loading
 * region announces itself (`aria-busy` on the container). Shimmer is off under reduced
 * motion (Feature 03 §8).
 */
export function Skeleton({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cx("block animate-pulse rounded-md bg-sunken motion-reduce:animate-none", className)}
    />
  );
}
