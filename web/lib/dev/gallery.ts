/**
 * Dev-only routes (`/dev/*`: the component gallery, test probes) render only when the
 * runtime env var `ENABLE_COMPONENT_GALLERY=1` is set: local, CI e2e and staging
 * (Feature 03 A3). `NODE_ENV` cannot be the switch, because staging is a production
 * build too. Read at request time, so pages using it must be dynamic.
 */
export function galleryEnabled(
  env: Readonly<Record<string, string | undefined>> = process.env,
): boolean {
  return env.ENABLE_COMPONENT_GALLERY === "1";
}
