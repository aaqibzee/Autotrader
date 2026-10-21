/**
 * The `next` parameter on sign-in redirects (Feature 03 §3, A10): a same-origin relative
 * path, or `/`. Anything that a browser could resolve to another origin is refused, so the
 * sign-in page cannot be used as an open redirect. Feature 04's sign-in page uses it.
 */
export const SAFE_NEXT_FALLBACK = "/";
const MAX_LENGTH = 2_048;
const PROBE_ORIGIN = "http://same-origin.invalid";

// Browsers strip tab/CR/LF from URLs before parsing, which turns `/\t/evil` into `//evil`.
function hasControlCharacter(value: string): boolean {
	for (let i = 0; i < value.length; i += 1) {
		const code = value.charCodeAt(i);
		if (code < 0x20 || code === 0x7f) return true;
	}
	return false;
}

// `//host` is protocol-relative. Backslashes are refused outright: browsers treat `\` as
// `/`, so `/\host` is protocol-relative too.
function isSingleSlashPath(path: string): boolean {
	return path.startsWith("/") && !path.startsWith("//");
}

export function safeNextPath(raw: string | null | undefined): string {
	if (!raw || raw.length > MAX_LENGTH) return SAFE_NEXT_FALLBACK;
	if (hasControlCharacter(raw) || raw.includes("\\") || !isSingleSlashPath(raw)) {
		return SAFE_NEXT_FALLBACK;
	}

	// A single-slash path always parses against the probe origin and keeps it. Parsing is
	// for normalisation: `/..//evil` resolves to the path `//evil`, so re-check the result.
	const url = new URL(raw, PROBE_ORIGIN);
	const path = `${url.pathname}${url.search}${url.hash}`;
	return isSingleSlashPath(path) ? path : SAFE_NEXT_FALLBACK;
}
