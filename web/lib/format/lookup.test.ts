// @vitest-environment node
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { matchesLookup, normaliseLookup } from "./lookup";

// Shared with backend/tests/test_lookup_contract.py (Feature 02 A9, Feature 03 slice 3.8).
const contract = JSON.parse(
  readFileSync(
    fileURLToPath(
      new URL("../../../ops/contracts/lookup-normal-form.json", import.meta.url),
    ),
    "utf8",
  ),
) as { cases: Array<[string, string]> };

describe("normaliseLookup", () => {
  it("has cases to check", () => {
    expect(contract.cases.length).toBeGreaterThanOrEqual(10);
  });

  it.each(contract.cases)("%j -> %j, as the server does", (raw, expected) => {
    expect(normaliseLookup(raw)).toBe(expected);
  });
});

describe("matchesLookup", () => {
  it("ignores accents, case, spaces and hyphens", () => {
    expect(matchesLookup("Citroën", "citroen")).toBe(true);
    expect(matchesLookup("Mercedes-Benz", "mercedes ben")).toBe(true);
    expect(matchesLookup("Škoda", "SKO")).toBe(true);
  });

  it("matches inside the name, and an empty query matches everything", () => {
    expect(matchesLookup("Land Rover", "rover")).toBe(true);
    expect(matchesLookup("Land Rover", "")).toBe(true);
  });

  it("keeps symbols meaningful", () => {
    expect(matchesLookup("Ka", "ka+")).toBe(false);
    expect(matchesLookup("Ka+", "ka+")).toBe(true);
  });

  it("rejects non-matches", () => {
    expect(matchesLookup("Ford", "vauxhall")).toBe(false);
  });
});
