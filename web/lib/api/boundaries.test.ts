import fs from "node:fs";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";

type Violation = { rule: string; chain: string[] };
type BoundaryModule = {
  findBoundaryViolations: (
    webRoot?: string,
    options?: { typescriptFrom?: string },
  ) => Violation[];
};

const webRoot = path.resolve(__dirname, "..", "..");
// Node's own require, not Vite's import: the checker is plain .mjs outside the web root,
// which Vite refuses to load. Node >= 22.12 can require() an ES module without top-level await.
const nodeRequire = createRequire(import.meta.url);
const { findBoundaryViolations } = nodeRequire(
  path.join(webRoot, "..", "ops", "ci", "check_web_boundaries.mjs"),
) as BoundaryModule;

const fixtures: string[] = [];

/** A throwaway web tree: `files` maps relative path -> source. */
function fixture(files: Record<string, string>): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "web-boundaries-"));
  fixtures.push(root);
  for (const [file, source] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(root, file)), { recursive: true });
    fs.writeFileSync(path.join(root, file), source, "utf8");
  }
  return root;
}

const SESSION = {
  "lib/api/session.ts": "export const getSessionApi = () => {};\n",
};
const PUBLIC = {
  "lib/api/public.ts": "export const getPublicApi = () => {};\n",
};

function check(files: Record<string, string>) {
  return findBoundaryViolations(fixture(files), { typescriptFrom: webRoot });
}

afterEach(() => {
  for (const root of fixtures.splice(0))
    fs.rmSync(root, { recursive: true, force: true });
});

describe("check_web_boundaries (Feature 03 A4)", () => {
  it("the real web tree has no violations", () => {
    expect(findBoundaryViolations(webRoot)).toEqual([]);
  });

  it("flags a public page importing the session client directly", () => {
    const violations = check({
      ...SESSION,
      "app/(public)/page.tsx":
        'import { getSessionApi } from "@/lib/api/session";\n',
    });
    expect(violations.map((v) => v.chain)).toEqual([
      ["app/(public)/page.tsx", "lib/api/session.ts"],
    ]);
  });

  it("flags a chain through a shared component, with relative and alias imports", () => {
    const violations = check({
      ...SESSION,
      "app/(public)/cars/page.tsx":
        'import { Card } from "../../../components/card";\n',
      "components/card.tsx":
        'export { Header as Card } from "@/components/header";\n',
      "components/header.tsx":
        'import "@/lib/api/session";\nexport const Header = 1;\n',
    });
    expect(violations.map((v) => v.chain)).toEqual([
      [
        "app/(public)/cars/page.tsx",
        "components/card.tsx",
        "components/header.tsx",
        "lib/api/session.ts",
      ],
    ]);
  });

  it("flags dynamic imports", () => {
    const violations = check({
      ...SESSION,
      "app/(public)/page.tsx":
        'export const load = () => import("@/lib/api/session");\n',
    });
    expect(violations).toHaveLength(1);
  });

  it("allows the public client, and the session client outside public routes", () => {
    expect(
      check({
        ...SESSION,
        ...PUBLIC,
        "app/(public)/page.tsx":
          'import { getPublicApi } from "@/lib/api/public";\n',
        "app/dealer/page.tsx":
          'import { getSessionApi } from "@/lib/api/session";\n',
      }),
    ).toEqual([]);
  });

  it("survives import cycles", () => {
    expect(
      check({
        ...SESSION,
        "app/(public)/page.tsx": 'import "@/components/a";\n',
        "components/a.ts": 'import "./b";\n',
        "components/b.ts": 'import "./a";\n',
      }),
    ).toEqual([]);
  });
});
