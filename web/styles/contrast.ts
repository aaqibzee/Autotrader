/** WCAG 2.2 contrast helpers for the token tests (Feature 03 §1). Pure, no DOM. */

const HEX = /^#(?:[0-9a-f]{3}|[0-9a-f]{6})$/i;
const COLOUR_TOKEN = /--color-([a-z0-9-]+)\s*:\s*([^;]+);/g;

/**
 * Reads `--color-<name>: <value>;` declarations from a stylesheet. Every value must be a
 * hex colour: anything else (oklch, rgb, a var reference) would escape the contrast check,
 * so it is an error rather than a skipped token. `--color-*: initial` is the palette reset.
 */
export function parseColourTokens(css: string): Map<string, string> {
  const tokens = new Map<string, string>();
  for (const [, name, rawValue] of css.matchAll(COLOUR_TOKEN)) {
    const value = rawValue!.trim();
    if (!HEX.test(value)) {
      throw new Error(
        `Colour token --color-${name} must be a hex colour, got "${value}"`,
      );
    }
    if (tokens.has(name!))
      throw new Error(`Colour token --color-${name} is declared twice`);
    tokens.set(name!, value.toLowerCase());
  }
  return tokens;
}

function channel(value: number): number {
  const c = value / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

export function relativeLuminance(hex: string): number {
  if (!HEX.test(hex)) throw new Error(`Not a hex colour: "${hex}"`);
  const digits =
    hex.length === 4
      ? [...hex.slice(1)].map((d) => d + d).join("")
      : hex.slice(1);
  const [r, g, b] = [0, 2, 4].map((i) =>
    channel(Number.parseInt(digits.slice(i, i + 2), 16)),
  );
  return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
}

export function contrastRatio(a: string, b: string): number {
  const [light, dark] = [relativeLuminance(a), relativeLuminance(b)].sort(
    (x, y) => y - x,
  );
  return (light! + 0.05) / (dark! + 0.05);
}
