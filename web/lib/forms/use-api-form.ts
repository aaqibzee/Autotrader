"use client";

import { ApiError, ApiNetworkError, ApiTimeoutError } from "@/lib/api/error";
import { problemUi } from "@/lib/api/problem-ui";
import { type ChangeEvent, type FormEvent, useRef, useState } from "react";
import type { z } from "./zod";
import {
  type ConflictChange,
  type ConflictField,
  conflictChanges,
} from "./conflict";
import type { IdempotentEndpoint } from "./endpoints";
import { apiFieldErrors, schemaFieldErrors } from "./field-errors";
import { afterAnswer, initialKeyState, keyForAttempt } from "./idempotency-key";

/**
 * Every form's submit plumbing (Feature 03 §3, slice 3.10):
 * - client validation with a zod schema, messages on their fields;
 * - a submit lock in a ref, so two clicks in one frame send one request;
 * - an `Idempotency-Key` for endpoints listed in `IDEMPOTENT_ENDPOINTS`, reused only to
 *   retry an unanswered identical request (lib/forms/idempotency-key.ts, A18);
 * - a 422's `errors[]` on fields, unknown fields at form level;
 * - a 409 `stale_update` as a conflict: what changed, "Reload theirs" or "Re-apply mine";
 * - any other failure as `problem`, for `ProblemView`;
 * - values kept on every failure.
 */
type Values = Record<string, unknown>;
type FieldName<V> = Extract<keyof V, string>;

export type ApiFormConflict = {
  current: Values;
  changes: ConflictChange[];
};

export type UseApiFormOptions<V extends Values, R> = {
  initialValues: V;
  /** Sends an `Idempotency-Key`; only endpoints reviewed for it are allowed. */
  idempotency?: IdempotentEndpoint;
  /** The optimistic-lock field "Re-apply mine" copies from the current version. */
  tokenField?: FieldName<V>;
  /** Fields shown in the conflict dialog, with their labels. */
  conflictFields?: Partial<Record<FieldName<V>, ConflictField>>;
  /** Prefix for field ids, so two forms on one page never share an id. */
  idPrefix?: string;
  onSuccess?: (result: R) => void;
  /** Mints keys; replaceable in tests. */
  mintKey?: () => string;
};

export type SubmitContext = { idempotencyKey?: string };

export function useApiForm<S extends z.ZodType<unknown, Values>, R>(
  schema: S,
  submit: (values: z.output<S>, context: SubmitContext) => Promise<R>,
  options: UseApiFormOptions<z.input<S>, R>,
) {
  type V = z.input<S>;
  type F = FieldName<V>;
  const fields = Object.keys(options.initialValues) as F[];
  const mintKey = options.mintKey ?? (() => crypto.randomUUID());

  const [values, setValues] = useState<V>(options.initialValues);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<F, string>>>(
    {},
  );
  const [formErrors, setFormErrors] = useState<string[]>([]);
  const [problem, setProblem] = useState<unknown>(undefined);
  const [conflict, setConflict] = useState<ApiFormConflict | undefined>(
    undefined,
  );
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<R | undefined>(undefined);

  const lock = useRef(false);
  // Minted when the form mounts (design §3); lazily, so one render mints one key.
  const keyState = useRef<ReturnType<typeof initialKeyState> | null>(null);
  keyState.current ??= initialKeyState(mintKey());

  const attempt = async (toSend: V) => {
    if (lock.current) return;
    lock.current = true;
    setSubmitting(true);
    try {
      const parsed = schema.safeParse(toSend);
      if (!parsed.success) {
        const mapped = schemaFieldErrors(parsed.error.issues, fields);
        setFieldErrors(mapped.fieldErrors);
        setFormErrors(mapped.formErrors);
        return;
      }
      setProblem(undefined);
      setFormErrors([]);
      let idempotencyKey: string | undefined;
      if (options.idempotency) {
        keyState.current = keyForAttempt(
          keyState.current!,
          JSON.stringify(parsed.data),
          mintKey,
        );
        idempotencyKey = keyState.current.key;
      }
      try {
        const response = await submit(parsed.data, { idempotencyKey });
        keyState.current = afterAnswer(keyState.current!);
        setFieldErrors({});
        setConflict(undefined);
        setResult(response);
        options.onSuccess?.(response);
      } catch (error) {
        // No answer: the request may have run. Keep the key, so a retry replays.
        if (
          !(
            error instanceof ApiNetworkError || error instanceof ApiTimeoutError
          )
        ) {
          keyState.current = afterAnswer(keyState.current!);
        }
        const kind = problemUi(error).kind;
        if (error instanceof ApiError && kind === "field-errors") {
          const mapped = apiFieldErrors(error.errors, fields);
          setFieldErrors(mapped.fieldErrors);
          setFormErrors(mapped.formErrors);
        } else if (
          error instanceof ApiError &&
          kind === "conflict" &&
          isRecord(error.extensions.current)
        ) {
          const current = error.extensions.current;
          setConflict({
            current,
            changes: conflictChanges(
              toSend,
              current,
              options.conflictFields ?? {},
            ),
          });
        } else {
          setProblem(error);
        }
      }
    } finally {
      lock.current = false;
      setSubmitting(false);
    }
  };

  const setValue = (name: F, value: unknown) => {
    setValues((current) => ({ ...current, [name]: value }));
    setFieldErrors((current) => {
      if (!(name in current)) return current;
      const next = { ...current };
      delete next[name];
      return next;
    });
  };

  return {
    values,
    fieldErrors,
    formErrors,
    problem,
    conflict,
    submitting,
    result,
    setValue,
    /** Spread onto a form: `<form onSubmit={form.handleSubmit}>`. */
    handleSubmit: (event?: FormEvent) => {
      event?.preventDefault();
      void attempt(values);
    },
    /** Retry after a `problem` (network error, timeout, 503): same values, same rules. */
    retry: () => void attempt(values),
    /** Conflict: take their version into the form and discard mine. */
    reloadTheirs: () => {
      if (!conflict) return;
      const theirs = Object.fromEntries(
        fields
          .filter((field) => field in conflict.current)
          .map((field) => [field, conflict.current[field]]),
      );
      setValues((current) => ({ ...current, ...theirs }));
      setConflict(undefined);
    },
    /** Conflict: keep my values, on top of their version's lock token. */
    reapplyMine: () => {
      if (!conflict) return;
      const token = options.tokenField;
      const mine = token
        ? { ...values, [token]: conflict.current[token] }
        : values;
      setValues(mine);
      setConflict(undefined);
      void attempt(mine);
    },
    dismissConflict: () => setConflict(undefined),
    /** Props for a text-like field from components/ui/inputs. */
    fieldProps: (name: F) => ({
      id: `${options.idPrefix ?? "form"}-${name}`,
      name,
      value: String(values[name] ?? ""),
      onChange: (event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
        setValue(name, event.target.value),
      error: fieldErrors[name],
    }),
  };
}

function isRecord(value: unknown): value is Values {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
