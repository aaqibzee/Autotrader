import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { contrastRatio, parseColourTokens, relativeLuminance } from "./contrast";
import { DECORATIVE, MIN_RATIO, PAIRINGS, type Pairing } from "./pairings";

const webRoot = path.resolve(__dirname, "..");
const tokensCss = fs.readFileSync(path.join(webRoot, "styles", "tokens.css"), "utf8");
const tokens = parseColourTokens(tokensCss);

/** Failures for a set of pairings, so the negative tests exercise the same rule. */
function pairingFailures(pairings: readonly Pairing[], palette: Map<string, string>): string[] {
  return pairings.flatMap(([fg, bg, kind]) => {
    const fgHex = palette.get(fg);
    const bgHex = palette.get(bg);
    if (!fgHex || !bgHex) return [`${fg} on ${bg}: unknown token`];
    const ratio = contrastRatio(fgHex, bgHex);
    return ratio < MIN_RATIO[kind] ? [`${fg} on ${bg} (${kind}): ${ratio.toFixed(2)}:1`] : [];
  });
}

describe("contrast maths", () => {
  it("matches the WCAG reference values", () => {
    expect(contrastRatio("#000000", "#ffffff")).toBeCloseTo(21, 5);
    expect(contrastRatio("#ffffff", "#ffffff")).toBeCloseTo(1, 5);
    // #767676 on white is the well-known 4.54:1 minimum grey.
    expect(contrastRatio("#767676", "#ffffff")).toBeCloseTo(4.54, 2);
    expect(relativeLuminance("#fff")).toBeCloseTo(1, 5);
  });

  it("refuses a non-hex colour", () => {
    expect(() => relativeLuminance("red")).toThrow(/hex/);
  });
});

describe("token parser", () => {
  it("rejects a token that is not hex, so it cannot escape the check", () => {
    expect(() => parseColourTokens("--color-ink: oklch(0.2 0.01 160);")).toThrow(/must be a hex/);
    expect(() => parseColourTokens("--color-ink: var(--other);")).toThrow(/must be a hex/);
  });

  it("rejects a duplicate token", () => {
    expect(() => parseColourTokens("--color-a: #000; --color-a: #fff;")).toThrow(/twice/);
  });

  it("skips the palette reset", () => {
    expect(parseColourTokens("--color-*: initial; --color-a: #000;")).toEqual(
      new Map([["a", "#000"]]),
    );
  });

  it("finds the tokens in tokens.css", () => {
    expect(tokens.size).toBeGreaterThan(30);
    expect(tokens.get("ink")).toBe("#111816");
  });
});

describe("design tokens (Feature 03 §1, A15)", () => {
  it("clears Tailwind's default palette", () => {
    expect(tokensCss).toMatch(/--color-\*\s*:\s*initial/);
  });

  it("every pairing meets WCAG 2.2 AA", () => {
    expect(pairingFailures(PAIRINGS, tokens)).toEqual([]);
  });

  it("every colour token is paired or declared decorative", () => {
    const used = new Set(PAIRINGS.flatMap(([fg, bg]) => [fg, bg]));
    const unpaired = [...tokens.keys()].filter((name) => !used.has(name) && !(name in DECORATIVE));
    expect(unpaired).toEqual([]);
  });

  it("decorative tokens exist", () => {
    expect(Object.keys(DECORATIVE).filter((name) => !tokens.has(name))).toEqual([]);
  });

  // Negative proofs: the rule above must be able to fail.
  it("reports a low-contrast pairing", () => {
    const palette = new Map([
      ["pale", "#999999"],
      ["white", "#ffffff"],
    ]);
    expect(pairingFailures([["pale", "white", "body"]], palette)).toEqual([
      "pale on white (body): 2.85:1",
    ]);
    // 2.85:1 is below the 3:1 UI minimum too.
    expect(pairingFailures([["pale", "white", "ui"]], palette)).toHaveLength(1);
  });

  it("reports a pairing that names an unknown token", () => {
    expect(pairingFailures([["nope", "surface", "body"]], tokens)).toEqual([
      "nope on surface: unknown token",
    ]);
  });
});

describe("no colour outside the tokens", () => {
  const sourceDirs = ["app", "components", "lib", "styles"];
  const skipDirs = new Set(["node_modules", ".next", "coverage"]);
  // A Tailwind arbitrary value holding a colour (`text-[#71972a]`, `shadow-[0_1px_rgba(…)]`,
  // `bg-[var(--x)]`) bypasses the cleared palette, so it is banned in source.
  const ARBITRARY_COLOUR = /-\[[^\]\s]*(?:#[0-9a-f]{3,8}\b|rgba?\(|hsla?\(|oklch\(|var\(--)/i;
  const CSS_COLOUR_LITERAL = /#[0-9a-f]{3,8}\b|rgba?\(|hsla?\(|oklch\(/i;

  function sourceFiles(dir: string): string[] {
    if (!fs.existsSync(dir)) return [];
    return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) return skipDirs.has(entry.name) ? [] : sourceFiles(full);
      return /\.(tsx?|css)$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name) ? [full] : [];
    });
  }

  const files = sourceDirs.flatMap((dir) => sourceFiles(path.join(webRoot, dir)));

  it("scans the source tree", () => {
    expect(files.some((file) => file.endsWith(path.join("app", "layout.tsx")))).toBe(true);
  });

  it("no Tailwind arbitrary colour values in components", () => {
    const offenders = files
      .filter((file) => /\.tsx?$/.test(file))
      .flatMap((file) =>
        fs
          .readFileSync(file, "utf8")
          .split("\n")
          .flatMap((line, i) =>
            ARBITRARY_COLOUR.test(line) ? [`${path.relative(webRoot, file)}:${i + 1}`] : [],
          ),
      );
    expect(offenders).toEqual([]);
  });

  it("no colour literals in stylesheets other than tokens.css", () => {
    const offenders = files
      .filter((file) => file.endsWith(".css") && !file.endsWith("tokens.css"))
      .filter((file) => CSS_COLOUR_LITERAL.test(fs.readFileSync(file, "utf8")));
    expect(offenders.map((file) => path.relative(webRoot, file))).toEqual([]);
  });

  it("the arbitrary-colour pattern catches each banned form", () => {
    for (const sample of [
      'className="text-[#71972a]"',
      'className="shadow-[0_16px_50px_rgba(23,33,31,0.06)]"',
      'className="bg-[var(--paper)]"',
      'className="border-[oklch(0.5_0.1_160)]"',
    ]) {
      expect(ARBITRARY_COLOUR.test(sample), sample).toBe(true);
    }
    expect(ARBITRARY_COLOUR.test('className="w-[min(100%-40px,1160px)]"')).toBe(false);
  });
});
