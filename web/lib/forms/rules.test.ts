import { describe, expect, it } from "vitest";
import { conflictChanges } from "./conflict";
import { IDEMPOTENT_ENDPOINTS } from "./endpoints";
import { apiFieldErrors, schemaFieldErrors } from "./field-errors";
import { afterAnswer, initialKeyState, keyForAttempt } from "./idempotency-key";

describe("Idempotency-Key lifecycle (A18)", () => {
  let counter = 0;
  const mint = () => `minted-${(counter += 1)}`;

  it("the first attempt uses the key minted at mount", () => {
    const state = keyForAttempt(initialKeyState("mount-key"), "{a}", mint);
    expect(state.key).toBe("mount-key");
  });

  it("an unanswered attempt retried with the same payload reuses the key", () => {
    const first = keyForAttempt(initialKeyState("mount-key"), "{a}", mint);
    // Network error or timeout: no afterAnswer.
    expect(keyForAttempt(first, "{a}", mint).key).toBe("mount-key");
  });

  it("an unanswered attempt retried with different values gets a new key", () => {
    const first = keyForAttempt(initialKeyState("mount-key"), "{a}", mint);
    expect(keyForAttempt(first, "{b}", mint).key).not.toBe("mount-key");
  });

  it("any answer, success or 4xx, spends the key, even for the same payload", () => {
    const answered = afterAnswer(
      keyForAttempt(initialKeyState("mount-key"), "{a}", mint),
    );
    const next = keyForAttempt(answered, "{a}", mint);
    expect(next.key).not.toBe("mount-key");
    expect(next.key).toMatch(/^minted-/);
  });

  it("only reviewed endpoints are listed", () => {
    expect(Object.keys(IDEMPOTENT_ENDPOINTS)).toEqual(["formProbe"]);
  });
});

describe("validation messages on fields", () => {
  const fields = ["name", "email"] as const;

  it("maps a 422's body.* fields, and unknown fields become form errors", () => {
    const mapped = apiFieldErrors(
      [
        {
          field: "body.name",
          code: "taken",
          message: "That name is already in use.",
        },
        {
          field: "body.name",
          code: "short",
          message: "A second message for name.",
        },
        { field: "email", code: "bad", message: "Enter an email." },
        {
          field: "body.dealer_id",
          code: "missing",
          message: "Choose a dealership.",
        },
      ],
      fields,
    );
    expect(mapped.fieldErrors).toEqual({
      name: "That name is already in use.",
      email: "Enter an email.",
    });
    expect(mapped.formErrors).toEqual(["Choose a dealership."]);
  });

  it("handles a 422 without errors[]", () => {
    expect(apiFieldErrors(undefined, fields)).toEqual({
      fieldErrors: {},
      formErrors: [],
    });
    expect(apiFieldErrors(null, fields)).toEqual({
      fieldErrors: {},
      formErrors: [],
    });
  });

  it("maps schema issues by their first path segment; pathless ones are form errors", () => {
    const mapped = schemaFieldErrors(
      [
        { path: ["email"], message: "Enter an email." },
        { path: [], message: "Something about the whole form." },
      ],
      fields,
    );
    expect(mapped.fieldErrors).toEqual({ email: "Enter an email." });
    expect(mapped.formErrors).toEqual(["Something about the whole form."]);
  });
});

describe("conflict changes", () => {
  it("lists labelled fields that differ, formatted, and ignores the rest", () => {
    const changes = conflictChanges(
      {
        name: "Mine",
        price_pence: "1000000",
        email: "a@b.co",
        updated_at: "old",
      },
      {
        name: "Theirs",
        price_pence: 1_050_000,
        email: "a@b.co",
        updated_at: "new",
      },
      {
        name: { label: "Name" },
        price_pence: {
          label: "Price",
          format: (value) => `£${Number(value) / 100}`,
        },
        email: { label: "Email" },
        notes: undefined,
      },
    );
    expect(changes).toEqual([
      { field: "name", label: "Name", mine: "Mine", theirs: "Theirs" },
      {
        field: "price_pence",
        label: "Price",
        mine: "£10000",
        theirs: "£10500",
      },
    ]);
  });

  it("treats missing and null as empty", () => {
    expect(
      conflictChanges({ name: null }, {}, { name: { label: "Name" } }),
    ).toEqual([]);
    expect(
      conflictChanges({}, { name: "Theirs" }, { name: { label: "Name" } }),
    ).toEqual([{ field: "name", label: "Name", mine: "", theirs: "Theirs" }]);
  });
});
