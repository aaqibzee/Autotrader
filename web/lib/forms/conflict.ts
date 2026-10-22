/**
 * What changed between the values a user submitted and the version someone else saved,
 * for `ConflictDialog` (409 `stale_update`, Feature 03 §3). Only fields the form labels
 * are compared, so internal members (`updated_at`, ids) never show up as "changes".
 */
export type ConflictField = {
  label: string;
  /** Formats a value for display, e.g. `formatPrice` for pence. Defaults to `String`. */
  format?: (value: unknown) => string;
};

export type ConflictChange = {
  field: string;
  label: string;
  mine: string;
  theirs: string;
};

const show = (value: unknown, format?: (value: unknown) => string) =>
  value === undefined || value === null
    ? ""
    : format
      ? format(value)
      : String(value);

export function conflictChanges(
  mine: Readonly<Record<string, unknown>>,
  current: Readonly<Record<string, unknown>>,
  fields: Readonly<Record<string, ConflictField | undefined>>,
): ConflictChange[] {
  const changes: ConflictChange[] = [];
  for (const [field, config] of Object.entries(fields)) {
    if (!config) continue;
    const ours = show(mine[field], config.format);
    const theirs = show(current[field], config.format);
    if (ours !== theirs)
      changes.push({ field, label: config.label, mine: ours, theirs });
  }
  return changes;
}
