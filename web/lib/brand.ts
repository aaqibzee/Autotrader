/**
 * Product name and wordmark, used by every layout, metadata and the maintenance page, so
 * a rename is one change. The public name is still open (Feature 03 slices, open decision
 * 6): "Autotrader" is a registered UK trade mark and must not ship on a launched beta.
 */
export const BRAND = {
  name: "Autotrader",
  /** Wordmark text; the trailing dot is drawn in the brand colour. */
  wordmark: "AUTOTRADER",
  description: "The foundation for a UK used-car marketplace.",
} as const;
