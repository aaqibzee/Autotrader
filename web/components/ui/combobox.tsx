"use client";

import { matchesLookup } from "@/lib/format/lookup";
import type { Key, ReactNode } from "react";
import {
  ComboBox as AriaComboBox,
  Button as AriaButton,
  Input,
  Label,
  ListBox,
  ListBoxItem,
  Popover,
  Text,
} from "react-aria-components";
import { Spinner } from "./button";
import { cx } from "./cx";
import { controlBorder } from "./field";

/**
 * Searchable single choice, e.g. make and model (Feature 03 §2). Typing filters the
 * list in the lookup normal form (Feature 02 A9), so "citroen" finds "Citroën" and
 * "mercedes benz" finds "Mercedes-Benz", the way the API matches them.
 *
 * React Aria keeps focus in the input and points `aria-activedescendant` at the
 * highlighted option, so a screen reader hears each option as the arrows move.
 */
export type ComboboxItem = { id: string; name: string };

export type ComboboxProps = {
  id: string;
  label: ReactNode;
  items: readonly ComboboxItem[];
  selectedKey?: string | null;
  defaultSelectedKey?: string | null;
  onSelectionChange?: (key: string | null) => void;
  /** Shows a spinner and a loading message instead of "no matches" while items arrive. */
  isLoading?: boolean;
  /** Shown when the typed text matches nothing. */
  emptyMessage?: ReactNode;
  placeholder?: string;
  hint?: ReactNode;
  error?: ReactNode;
  isDisabled?: boolean;
  name?: string;
  className?: string;
};

export function Combobox({
  id,
  label,
  items,
  selectedKey,
  defaultSelectedKey,
  onSelectionChange,
  isLoading = false,
  emptyMessage = "No matches",
  placeholder,
  hint,
  error,
  isDisabled,
  name,
  className,
}: ComboboxProps) {
  return (
    <AriaComboBox
      className={cx("group", className)}
      defaultFilter={matchesLookup}
      defaultItems={items}
      defaultSelectedKey={defaultSelectedKey}
      id={id}
      isDisabled={isDisabled}
      isInvalid={Boolean(error)}
      name={name}
      onSelectionChange={
        onSelectionChange &&
        ((key: Key | null) => onSelectionChange(key === null ? null : String(key)))
      }
      selectedKey={selectedKey}
      // Without this, an empty filter result closes the list and the user sees nothing.
      allowsEmptyCollection
    >
      <Label className="block text-sm font-semibold text-ink">{label}</Label>
      <div
        className={cx(
          "relative mt-1 flex min-h-11 items-center rounded-md border bg-surface",
          "focus-within:border-focus",
          "group-data-disabled:cursor-not-allowed group-data-disabled:bg-sunken",
          controlBorder(Boolean(error)),
        )}
      >
        <Input
          className="min-h-11 w-full min-w-0 rounded-md bg-transparent px-3 text-base text-ink outline-none placeholder:text-ink-subtle disabled:cursor-not-allowed disabled:text-ink-muted"
          placeholder={placeholder}
        />
        {isLoading ? <Spinner className="mr-2 text-ink-muted" /> : null}
        <AriaButton
          aria-label="Show options"
          className="inline-flex size-11 shrink-0 items-center justify-center rounded-r-md text-ink-muted outline-none hover-state:text-ink data-focus-visible:outline-2 data-focus-visible:outline-focus"
        >
          <svg aria-hidden="true" className="size-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path d="M6 9l6 6 6-6" />
          </svg>
        </AriaButton>
      </div>
      {hint ? (
        <Text className="mt-1 block text-sm text-ink-muted" slot="description">
          {hint}
        </Text>
      ) : null}
      {error ? (
        <Text className="mt-1 block text-sm font-medium text-danger" slot="errorMessage">
          {error}
        </Text>
      ) : null}
      <Popover
        className="z-modal max-h-72 w-(--trigger-width) overflow-auto rounded-md border border-line bg-surface p-1 shadow-overlay outline-none"
        // A popover can open inside a sheet or modal, so it sits on the modal layer; as a
        // later portal it paints above the dialog that opened it.
        offset={4}
      >
        <ListBox<ComboboxItem>
          className="outline-none"
          renderEmptyState={() => (
            <p className="px-3 py-2 text-sm text-ink-muted" role="status">
              {isLoading ? "Loading…" : emptyMessage}
            </p>
          )}
        >
          {(item) => (
            <ListBoxItem
              className="flex min-h-11 cursor-pointer items-center rounded-sm px-3 text-base text-ink outline-none data-focused:bg-brand-tint data-selected:font-semibold"
              id={item.id}
              textValue={item.name}
            >
              {item.name}
            </ListBoxItem>
          )}
        </ListBox>
      </Popover>
    </AriaComboBox>
  );
}
