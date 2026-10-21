// Feature 02 A9's lookup normal form, so typed text matches taxonomy names the way the API
// does: strip accents, spell `&`/`+` out (so "Ka+" is not "Ka"), upper-case, keep only
// A-Z and 0-9. "Citroen" finds "Citroën"; "mercedes benz" finds "Mercedes-Benz".
//
// The server's version is normalise_lookup in backend/app/modules/taxonomy/naming.py.
// Both are tested against ops/contracts/lookup-normal-form.json.
const SYMBOL_WORDS: ReadonlyArray<readonly [string, string]> = [
  ["&", " and "],
  ["+", " plus "],
];

export function normaliseLookup(text: string): string {
  let spelled = text;
  for (const [symbol, word] of SYMBOL_WORDS) {
    spelled = spelled.replaceAll(symbol, word);
  }
  // NFKD splits "ë" into "e" plus a combining mark and folds "ﬁ" and full-width letters;
  // the final filter then drops the marks and everything else outside A-Z0-9.
  return spelled
    .normalize("NFKD")
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "");
}

/** True when the query, in normal form, occurs in the candidate. An empty query matches all. */
export function matchesLookup(candidate: string, query: string): boolean {
  return normaliseLookup(candidate).includes(normaliseLookup(query));
}
