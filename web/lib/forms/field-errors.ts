import type { ApiValidationError } from "@/lib/api/error";

/**
 * Puts validation messages on the fields they belong to (Feature 03 §3). A message for a
 * field the form does not show is never dropped: it becomes a form-level error.
 */
export type MappedErrors<F extends string> = {
  fieldErrors: Partial<Record<F, string>>;
  formErrors: string[];
};

function place<F extends string>(
  entries: ReadonlyArray<{ field: string; message: string }>,
  fields: readonly F[],
): MappedErrors<F> {
  const known = new Set<string>(fields);
  const fieldErrors: Partial<Record<F, string>> = {};
  const formErrors: string[] = [];
  for (const { field, message } of entries) {
    if (known.has(field)) {
      // The first message per field: one clear instruction beats a list.
      fieldErrors[field as F] ??= message;
    } else {
      formErrors.push(message);
    }
  }
  return { fieldErrors, formErrors };
}

/**
 * A 422's `errors[]`. FastAPI names body fields by location (`body.price_pence`), so the
 * `body.` prefix is dropped; anything else is matched as is.
 */
export function apiFieldErrors<F extends string>(
  errors: readonly ApiValidationError[] | null | undefined,
  fields: readonly F[],
): MappedErrors<F> {
  return place(
    (errors ?? []).map((error) => ({
      field: error.field.replace(/^body\./, ""),
      message: error.message,
    })),
    fields,
  );
}

/** Client-side schema issues, keyed by their top-level path segment. */
export function schemaFieldErrors<F extends string>(
  issues: ReadonlyArray<{ path: ReadonlyArray<PropertyKey>; message: string }>,
  fields: readonly F[],
): MappedErrors<F> {
  return place(
    issues.map((issue) => ({
      field: String(issue.path[0] ?? ""),
      message: issue.message,
    })),
    fields,
  );
}
