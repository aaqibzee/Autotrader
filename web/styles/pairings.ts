/**
 * Every foreground/background pairing used on the site (Feature 03 §1), checked against
 * WCAG 2.2 AA by styles/tokens.test.ts. Names are tokens from styles/tokens.css without
 * the `--color-` prefix.
 *
 * - `body`: text of any size, 4.5:1.
 * - `large`: text ≥ 24px, or ≥ 18.66px bold, 3:1.
 * - `ui`: control boundaries, focus rings and icons that carry meaning, 3:1 (SC 1.4.11).
 *
 * Adding a colour to a component means adding its pairing here first.
 */
export type PairingKind = "body" | "large" | "ui";

export type Pairing = readonly [foreground: string, background: string, kind: PairingKind];

export const MIN_RATIO: Record<PairingKind, number> = { body: 4.5, large: 3, ui: 3 };

const TEXT_BACKGROUNDS = ["surface", "canvas"] as const;

export const PAIRINGS: readonly Pairing[] = [
  // Neutral text on the two page backgrounds.
  ...["ink", "ink-soft", "ink-muted", "ink-subtle"].flatMap((ink) =>
    TEXT_BACKGROUNDS.map((bg): Pairing => [ink, bg, "body"]),
  ),
  ["ink", "sunken", "body"],
  ["ink-muted", "sunken", "body"],

  // Links and brand text.
  ["brand-strong", "surface", "body"],
  ["brand-strong", "canvas", "body"],
  ["brand-strong", "brand-tint", "body"],

  // Filled buttons.
  ["surface", "brand", "body"],
  ["surface", "brand-strong", "body"],
  ["surface", "danger", "body"],
  ["surface", "ink", "body"],
  ["ink", "signal", "body"],

  // Control boundaries and focus.
  ["border-strong", "surface", "ui"],
  ["border-strong", "canvas", "ui"],
  ["focus", "surface", "ui"],
  ["focus", "canvas", "ui"],
  ["brand", "surface", "ui"],

  // Semantic messages: text on its tint, and the strong colour as text on white.
  ...(["success", "warning", "danger", "info"] as const).flatMap((tone): Pairing[] => [
    [tone, `${tone}-tint`, "body"],
    [tone, "surface", "body"],
  ]),

  // Price indicator badges.
  ...(["great", "good", "fair", "high", "none"] as const).map(
    (rating): Pairing => [`price-${rating}`, `price-${rating}-tint`, "body"],
  ),
];

/**
 * Tokens that never carry information on their own, so need no ratio. Each says why.
 * A control whose only boundary is one of these would fail SC 1.4.11: use `border-strong`.
 */
export const DECORATIVE: Readonly<Record<string, string>> = {
  line: "Dividers and card outlines; never the only boundary of a control.",
};
