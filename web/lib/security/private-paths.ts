/**
 * Signed-in surfaces (Feature 03 §6). Middleware gives every response under them
 * `Cache-Control: private, no-store` and `X-Robots-Tag: noindex`, so nothing personal is
 * stored by a browser cache or the edge, or indexed. Matches whole path segments only:
 * `/dealers-near-me` is public.
 */
const PRIVATE_PREFIX = /^\/(?:dealer|account|admin)(?:\/|$)/;

export function isPrivatePath(pathname: string): boolean {
  return PRIVATE_PREFIX.test(pathname);
}
