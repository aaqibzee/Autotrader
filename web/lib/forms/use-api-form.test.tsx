import { ApiError, ApiNetworkError, ApiTimeoutError } from "@/lib/api/error";
import { act, renderHook } from "@testing-library/react";
import type { ChangeEvent } from "react";
import { describe, expect, it, vi } from "vitest";
import { z } from "@/lib/forms/zod";
import { type SubmitContext, useApiForm } from "./use-api-form";

const schema = z.object({
  name: z.string().min(2, "Enter at least 2 characters."),
  price_pence: z.coerce.number<string>().int(),
  updated_at: z.string(),
});
type Out = z.output<typeof schema>;

const initialValues = {
  name: "Ford Fiesta",
  price_pence: "1249500",
  updated_at: "t1",
};

function setup(
  submit: (values: Out, context: SubmitContext) => Promise<unknown>,
  extra: Partial<Parameters<typeof useApiForm<typeof schema, unknown>>[2]> = {},
) {
  let minted = 0;
  const onSuccess = vi.fn();
  const hook = renderHook(() =>
    useApiForm(schema, submit, {
      initialValues,
      idempotency: "formProbe",
      tokenField: "updated_at",
      conflictFields: { name: { label: "Name" } },
      mintKey: () => `key-${(minted += 1)}`,
      onSuccess,
      ...extra,
    }),
  );
  const submitNow = async () => {
    await act(async () => {
      hook.result.current.handleSubmit();
    });
  };
  return { ...hook, onSuccess, submitNow };
}

const keysSent = (submit: ReturnType<typeof vi.fn>) =>
  submit.mock.calls.map((call) => (call[1] as SubmitContext).idempotencyKey);

describe("useApiForm", () => {
  it("validates on the client and puts messages on fields, without sending", async () => {
    const submit = vi.fn();
    const { result, submitNow } = setup(submit);
    act(() => result.current.setValue("name", "F"));
    await submitNow();
    expect(submit).not.toHaveBeenCalled();
    expect(result.current.fieldErrors).toEqual({
      name: "Enter at least 2 characters.",
    });

    // Editing the field clears its message; editing another leaves state alone.
    act(() => result.current.setValue("name", "Fo"));
    expect(result.current.fieldErrors).toEqual({});
    act(() => result.current.setValue("price_pence", "100"));
    expect(result.current.fieldErrors).toEqual({});
  });

  it("two submits in one frame send one request", async () => {
    let finish: (value: unknown) => void = () => {};
    const submit = vi.fn(() => new Promise((resolve) => (finish = resolve)));
    const { result } = setup(submit);
    await act(async () => {
      result.current.handleSubmit();
      result.current.handleSubmit();
    });
    expect(submit).toHaveBeenCalledOnce();
    expect(result.current.submitting).toBe(true);
    await act(async () => finish({ ok: true }));
    expect(result.current.submitting).toBe(false);
  });

  it("sends parsed values with the mount key; success spends the key", async () => {
    const submit = vi.fn(async (values: Out) => ({ saved: values.name }));
    const { result, onSuccess, submitNow } = setup(submit);
    await submitNow();
    expect(submit.mock.calls[0]?.[0]).toEqual({
      name: "Ford Fiesta",
      price_pence: 1_249_500,
      updated_at: "t1",
    });
    expect(onSuccess).toHaveBeenCalledWith({ saved: "Ford Fiesta" });
    expect(result.current.result).toEqual({ saved: "Ford Fiesta" });
    await submitNow();
    expect(keysSent(submit)).toEqual(["key-1", "key-2"]);
  });

  it.each([
    ["a network error", new ApiNetworkError(new TypeError("Failed to fetch"))],
    ["a timeout", new ApiTimeoutError(10_000)],
  ])(
    "after %s the values stay and retry reuses the key",
    async (_name, failure) => {
      const submit = vi
        .fn()
        .mockRejectedValueOnce(failure)
        .mockResolvedValueOnce({ ok: true });
      const { result } = setup(submit);
      act(() => result.current.setValue("name", "Ford Focus"));
      await act(async () => result.current.handleSubmit());
      expect(result.current.problem).toBe(failure);
      expect(result.current.values.name).toBe("Ford Focus");

      await act(async () => result.current.retry());
      expect(keysSent(submit)).toEqual(["key-1", "key-1"]);
      expect(result.current.problem).toBeUndefined();
    },
  );

  it("a 422 lands on fields, an unknown field at form level, and spends the key", async () => {
    const failure = new ApiError(
      {
        code: "invalid_input",
        errors: [
          {
            field: "body.name",
            code: "taken",
            message: "That name is already in use.",
          },
          {
            field: "body.dealer_id",
            code: "missing",
            message: "Choose a dealership.",
          },
        ],
      },
      422,
    );
    const submit = vi
      .fn()
      .mockRejectedValueOnce(failure)
      .mockResolvedValueOnce({});
    const { result, submitNow } = setup(submit);
    await submitNow();
    expect(result.current.fieldErrors).toEqual({
      name: "That name is already in use.",
    });
    expect(result.current.formErrors).toEqual(["Choose a dealership."]);
    expect(result.current.problem).toBeUndefined();
    await submitNow();
    expect(keysSent(submit)).toEqual(["key-1", "key-2"]);
  });

  it("a 409 opens a conflict; reload theirs takes their values", async () => {
    const current = {
      name: "Ford Fiesta ST",
      price_pence: 1_299_500,
      updated_at: "t2",
    };
    const submit = vi.fn().mockRejectedValue(
      new ApiError({ code: "stale_update" }, 409, undefined, {
        extensions: { current },
      }),
    );
    const { result, submitNow } = setup(submit);
    act(() => result.current.setValue("name", "Mine"));
    await submitNow();
    expect(result.current.conflict?.changes).toEqual([
      { field: "name", label: "Name", mine: "Mine", theirs: "Ford Fiesta ST" },
    ]);

    act(() => result.current.reloadTheirs());
    expect(result.current.conflict).toBeUndefined();
    expect(result.current.values).toEqual({
      name: "Ford Fiesta ST",
      price_pence: 1_299_500,
      updated_at: "t2",
    });
  });

  it("re-apply mine resubmits my values on their token", async () => {
    const current = { name: "Theirs", price_pence: 1, updated_at: "t2" };
    const submit = vi
      .fn()
      .mockRejectedValueOnce(
        new ApiError({ code: "stale_update" }, 409, undefined, {
          extensions: { current },
        }),
      )
      .mockResolvedValueOnce({ ok: true });
    const { result, submitNow } = setup(submit);
    act(() => result.current.setValue("name", "Mine"));
    await submitNow();
    await act(async () => result.current.reapplyMine());
    expect(submit.mock.calls[1]?.[0]).toMatchObject({
      name: "Mine",
      updated_at: "t2",
    });
    expect(result.current.conflict).toBeUndefined();
    expect(keysSent(submit)).toEqual(["key-1", "key-2"]);
  });

  it("re-apply mine without a token field resubmits the values as they are", async () => {
    const submit = vi
      .fn()
      .mockRejectedValueOnce(
        new ApiError({ code: "stale_update" }, 409, undefined, {
          extensions: { current: { name: "Theirs" } },
        }),
      )
      .mockResolvedValueOnce({});
    const { result, submitNow } = setup(submit, {
      tokenField: undefined,
      conflictFields: undefined,
    });
    await submitNow();
    expect(result.current.conflict?.changes).toEqual([]);
    await act(async () => result.current.reapplyMine());
    expect(submit.mock.calls[1]?.[0]).toMatchObject({ updated_at: "t1" });
  });

  it("conflict actions do nothing without a conflict; dismiss closes one", async () => {
    const submit = vi.fn().mockRejectedValue(
      new ApiError({ code: "stale_update" }, 409, undefined, {
        extensions: { current: { name: "x" } },
      }),
    );
    const { result, submitNow } = setup(submit);
    act(() => {
      result.current.reloadTheirs();
      result.current.reapplyMine();
    });
    expect(submit).not.toHaveBeenCalled();
    await submitNow();
    act(() => result.current.dismissConflict());
    expect(result.current.conflict).toBeUndefined();
  });

  it("a 409 without `current`, a 503 and unknown errors become a problem", async () => {
    for (const failure of [
      new ApiError({ code: "stale_update" }, 409),
      new ApiError({ code: "integration_unavailable" }, 503),
      new Error("boom"),
    ]) {
      const submit = vi.fn().mockRejectedValue(failure);
      const { result, submitNow, unmount } = setup(submit);
      await submitNow();
      expect(result.current.problem).toBe(failure);
      expect(result.current.conflict).toBeUndefined();
      unmount();
    }
  });

  it("sends no key for an endpoint not listed as idempotent", async () => {
    const submit = vi.fn(async () => ({}));
    const { submitNow } = setup(submit, { idempotency: undefined });
    await submitNow();
    expect(keysSent(submit)).toEqual([undefined]);
  });

  it("mints real UUIDs by default", async () => {
    const submit = vi.fn(async () => ({}));
    const { submitNow } = setup(submit, { mintKey: undefined });
    await submitNow();
    expect(keysSent(submit)[0]).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("fieldProps wires a field, and handleSubmit prevents the native submit", () => {
    const { result } = renderHook(() =>
      useApiForm(schema, async () => ({}), {
        initialValues: {
          ...initialValues,
          name: undefined as unknown as string,
        },
      }),
    );
    const props = result.current.fieldProps("name");
    expect(props).toMatchObject({ id: "form-name", name: "name", value: "" });
    act(() =>
      props.onChange({
        target: { value: "Kia" },
      } as ChangeEvent<HTMLInputElement>),
    );
    expect(result.current.values.name).toBe("Kia");

    const event = { preventDefault: vi.fn() };
    act(() => result.current.handleSubmit(event as never));
    expect(event.preventDefault).toHaveBeenCalled();
  });
});
