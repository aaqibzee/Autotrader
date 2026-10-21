/** Joins class names, skipping falsy values. Deliberately tiny: no dependency, no merging. */
export function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}
