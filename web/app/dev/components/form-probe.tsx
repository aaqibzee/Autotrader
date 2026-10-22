"use client";

import { Button } from "@/components/ui/button";
import { ConflictDialog } from "@/components/ui/conflict-dialog";
import { Select, TextInput } from "@/components/ui/inputs";
import { ProblemView } from "@/components/ui/problem-view";
import { CLIENT_TIMEOUT_MS } from "@/lib/api/client";
import { requestApi } from "@/lib/api/response";
import { formatPrice } from "@/lib/format";
import { useApiForm } from "@/lib/forms/use-api-form";
import { useEffect, useState } from "react";
import { z } from "@/lib/forms/zod";

/**
 * The form probe (Feature 03 slice 3.10): one form wired to the dev-only backend route
 * `/api/v1/dev/form-probe/{id}`, so the e2e suite can drive every `useApiForm` path
 * against the real middleware. Open with `?probe=<id>` to choose the record; the e2e
 * suite does, so it can read the execution counts back.
 */
type ProbeRecord = {
  name: string;
  email: string;
  price_pence: number;
  updated_at: string;
};

const MODES = [
  { value: "ok", label: "Save normally" },
  { value: "unavailable", label: "503 integration unavailable" },
  { value: "rate_limited", label: "429 rate limited" },
  { value: "hang", label: "Hang (no answer for 15 s)" },
];

const schema = z.object({
  name: z
    .string()
    .trim()
    .min(2, "Enter at least 2 characters.")
    .max(60, "Use 60 characters or fewer."),
  email: z.email("Enter an email address like name@example.com."),
  price_pence: z.coerce
    .number<string>("Enter a price in pence.")
    .int("Enter whole pence.")
    .min(0, "The price cannot be negative."),
  updated_at: z.string(),
  mode: z.enum(["ok", "unavailable", "rate_limited", "hang"]),
});

const probePath = (id: string) => `/api/v1/dev/form-probe/${id}`;

export function FormProbe() {
  const [probe, setProbe] = useState<{
    id: string;
    record: ProbeRecord;
  } | null>(null);
  const [loadError, setLoadError] = useState<unknown>(undefined);

  useEffect(() => {
    const id =
      new URLSearchParams(window.location.search).get("probe") ??
      `probe-${crypto.randomUUID().slice(0, 8)}`;
    requestApi<ProbeRecord>(probePath(id), {
      timeoutMs: CLIENT_TIMEOUT_MS,
    }).then((record) => setProbe({ id, record }), setLoadError);
  }, []);

  if (loadError) return <ProblemView error={loadError} headingLevel={3} />;
  if (!probe)
    return <p className="text-ink-muted">Loading the probe record…</p>;
  return <ProbeForm id={probe.id} record={probe.record} />;
}

function ProbeForm({ id, record }: { id: string; record: ProbeRecord }) {
  const [saved, setSaved] = useState<ProbeRecord | undefined>(undefined);
  const form = useApiForm(
    schema,
    (values, { idempotencyKey }) =>
      requestApi<ProbeRecord>(probePath(id), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
        },
        body: JSON.stringify(values),
        timeoutMs: CLIENT_TIMEOUT_MS,
      }),
    {
      initialValues: {
        name: record.name,
        email: record.email,
        price_pence: String(record.price_pence),
        updated_at: record.updated_at,
        mode: "ok" as "ok" | "unavailable" | "rate_limited" | "hang",
      },
      idempotency: "formProbe",
      idPrefix: "probe",
      tokenField: "updated_at",
      conflictFields: {
        name: { label: "Name" },
        email: { label: "Email" },
        price_pence: {
          label: "Price",
          format: (value) => formatPrice(Number(value)),
        },
      },
      onSuccess: (result) => {
        setSaved(result);
        // The next save must carry the new lock token.
        form.setValue("updated_at", result.updated_at);
      },
    },
  );

  return (
    <div className="grid max-w-lg gap-4" data-probe-id={id}>
      <form className="grid gap-4" noValidate onSubmit={form.handleSubmit}>
        <TextInput
          {...form.fieldProps("name")}
          hint='"Taken" gets a server-side 422.'
          label="Name"
        />
        <TextInput {...form.fieldProps("email")} label="Email" type="email" />
        <TextInput
          {...form.fieldProps("price_pence")}
          inputMode="numeric"
          label="Price (pence)"
        />
        <Select
          {...form.fieldProps("mode")}
          label="What the API should do"
          options={MODES}
        />
        {form.formErrors.length > 0 ? (
          <div
            className="rounded-md border border-danger bg-danger-tint px-4 py-3 text-danger"
            role="alert"
          >
            {form.formErrors.map((message) => (
              <p key={message}>{message}</p>
            ))}
          </div>
        ) : null}
        <div className="flex flex-wrap gap-3">
          <Button loading={form.submitting} type="submit">
            Save
          </Button>
          <Button
            onClick={() => {
              void requestApi(`${probePath(id)}/touch`, {
                method: "POST",
                timeoutMs: CLIENT_TIMEOUT_MS,
              });
            }}
            variant="secondary"
          >
            Simulate someone else&rsquo;s edit
          </Button>
        </div>
      </form>

      {form.problem ? (
        <ProblemView
          continueAction={
            <Button onClick={() => form.setValue("mode", "ok")}>
              Enter details manually
            </Button>
          }
          error={form.problem}
          headingLevel={3}
          onRetry={form.retry}
        />
      ) : null}

      <p aria-live="polite" className="text-sm text-success" role="status">
        {saved && !form.problem ? `Saved “${saved.name}”.` : ""}
      </p>

      <ConflictDialog
        conflict={form.conflict}
        onDismiss={form.dismissConflict}
        onReapplyMine={form.reapplyMine}
        onReloadTheirs={form.reloadTheirs}
      />
    </div>
  );
}
