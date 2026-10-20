/**
 * Content Security Policy for every page (Feature 01 §11), built per request with a nonce.
 *
 * Styles are split by kind (Feature 03 A2). Stylesheets and `<style>` elements need
 * `'self'` or the nonce. Style *attributes* are allowed inline: nonces never apply to
 * attributes, and React Aria server-renders them (visually hidden native inputs, slider
 * thumbs, overlay positions), which React does not re-apply on hydration. An attribute
 * cannot run script, and any `url()` in one is still governed by `img-src`/`font-src`.
 * `style-src` stays as the fallback for browsers without the split directives.
 */
export type CspOptions = {
  nonce: string;
  development: boolean;
  imageCdnOrigin?: string;
  errorIngestOrigin?: string;
  uploadsBucketOrigin?: string;
};

/** An origin from config, or undefined: https only, except loopback for local dev. */
export function configuredOrigin(value: string | undefined): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    if (url.protocol !== "https:" && url.hostname !== "localhost" && url.hostname !== "127.0.0.1") {
      return undefined;
    }
    return url.origin;
  } catch {
    return undefined;
  }
}

function sources(...values: Array<string | undefined>): string {
  return values.filter((value): value is string => Boolean(value)).join(" ");
}

export function buildContentSecurityPolicy(options: CspOptions): string {
  const nonce = `'nonce-${options.nonce}'`;
  const imageCdn = configuredOrigin(options.imageCdnOrigin);
  const errorIngest = configuredOrigin(options.errorIngestOrigin);
  const uploadsBucket = configuredOrigin(options.uploadsBucketOrigin);

  return [
    "default-src 'self'",
    `script-src ${sources("'self'", nonce, "'strict-dynamic'", options.development ? "'unsafe-eval'" : undefined)}`,
    `style-src ${sources("'self'", nonce)}`,
    `style-src-elem ${sources("'self'", nonce)}`,
    "style-src-attr 'unsafe-inline'",
    `img-src ${sources("'self'", "data:", "blob:", imageCdn)}`,
    `connect-src ${sources("'self'", errorIngest, uploadsBucket)}`,
    "font-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}
