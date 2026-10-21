import type {
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
} from "react";
import { cx } from "./cx";
import {
  FieldError,
  FieldHint,
  FieldLabel,
  type FieldProps,
  controlA11y,
  controlBorder,
  describedBy,
} from "./field";

type Force = { "data-force"?: string };

const textControl = (invalid: boolean, className?: string) =>
  cx(
    "mt-1 block min-h-11 w-full rounded-md border bg-surface px-3 text-base text-ink",
    "placeholder:text-ink-subtle disabled:cursor-not-allowed disabled:bg-sunken disabled:text-ink-muted",
    "focus-state:border-focus",
    controlBorder(invalid),
    className,
  );

export type TextInputProps = FieldProps &
  Omit<InputHTMLAttributes<HTMLInputElement>, "id"> &
  Force & { inputClassName?: string };

/** Labelled text input. 44px tall: the primary input on a phone. */
export function TextInput({
  id,
  label,
  hint,
  error,
  className,
  inputClassName,
  ...rest
}: TextInputProps) {
  return (
    <div className={className}>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <input
        {...rest}
        {...controlA11y({ id, hint, error })}
        className={textControl(Boolean(error), inputClassName)}
      />
      <FieldHint id={id}>{hint}</FieldHint>
      <FieldError id={id}>{error}</FieldError>
    </div>
  );
}

export type SelectOption = { value: string; label: string; disabled?: boolean };

export type SelectProps = FieldProps &
  Omit<SelectHTMLAttributes<HTMLSelectElement>, "id"> &
  Force & { options: readonly SelectOption[]; placeholder?: string };

/**
 * Native `<select>`: the platform picker is the best control on a phone and needs no
 * script. The searchable make/model picker is the Combobox (slice 3.8).
 */
export function Select({
  id,
  label,
  hint,
  error,
  options,
  placeholder,
  className,
  ...rest
}: SelectProps) {
  return (
    <div className={className}>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <select
        {...rest}
        {...controlA11y({ id, hint, error })}
        className={textControl(Boolean(error), "pr-8")}
      >
        {placeholder !== undefined && <option value="">{placeholder}</option>}
        {options.map((option) => (
          <option
            disabled={option.disabled}
            key={option.value}
            value={option.value}
          >
            {option.label}
          </option>
        ))}
      </select>
      <FieldHint id={id}>{hint}</FieldHint>
      <FieldError id={id}>{error}</FieldError>
    </div>
  );
}

// Native checkbox, radio and switch: fully keyboard- and screen-reader-accessible with no
// script and no style attributes (design §2 reserves React Aria for the complex widgets).
const box =
  "size-5 shrink-0 cursor-pointer accent-brand disabled:cursor-not-allowed focus-state:outline-2";
// The whole row is the click target, comfortably over 24×24.
const choiceRow =
  "flex min-h-11 cursor-pointer items-center gap-3 text-base text-ink";

export type CheckboxProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "id" | "type"
> &
  Force & { id: string; label: ReactNode; hint?: ReactNode; error?: ReactNode };

export function Checkbox({
  id,
  label,
  hint,
  error,
  className,
  ...rest
}: CheckboxProps) {
  return (
    <div className={className}>
      <label className={choiceRow} htmlFor={id}>
        <input
          {...rest}
          {...controlA11y({ id, hint, error })}
          className={box}
          type="checkbox"
        />
        <span>{label}</span>
      </label>
      <FieldHint id={id}>{hint}</FieldHint>
      <FieldError id={id}>{error}</FieldError>
    </div>
  );
}

export type ToggleProps = CheckboxProps;

/** On/off setting that applies immediately (`role="switch"`); use Checkbox inside forms. */
export function Toggle({
  id,
  label,
  hint,
  error,
  className,
  ...rest
}: ToggleProps) {
  return (
    <div className={className}>
      <label className={cx(choiceRow, "justify-between")} htmlFor={id}>
        <span>{label}</span>
        <input
          {...rest}
          {...controlA11y({ id, hint, error })}
          className={cx(
            "relative h-7 w-12 shrink-0 cursor-pointer appearance-none rounded-full border border-border-strong bg-sunken transition-colors",
            "before:absolute before:top-0.5 before:left-0.5 before:size-5 before:rounded-full before:bg-ink-muted before:transition-transform",
            "checked:border-brand checked:bg-brand checked:before:translate-x-5 checked:before:bg-surface",
            "disabled:cursor-not-allowed disabled:opacity-50 motion-reduce:transition-none motion-reduce:before:transition-none",
          )}
          role="switch"
          type="checkbox"
        />
      </label>
      <FieldHint id={id}>{hint}</FieldHint>
      <FieldError id={id}>{error}</FieldError>
    </div>
  );
}

export type RadioGroupProps = {
  /** Used for the input `name` and as the id prefix. */
  name: string;
  legend: ReactNode;
  options: readonly SelectOption[];
  defaultValue?: string;
  value?: string;
  onChange?: (value: string) => void;
  hint?: ReactNode;
  error?: ReactNode;
  disabled?: boolean;
  className?: string;
};

/** A set of radios in a `fieldset` with a visible `legend`. */
export function RadioGroup({
  name,
  legend,
  options,
  defaultValue,
  value,
  onChange,
  hint,
  error,
  disabled,
  className,
}: RadioGroupProps) {
  return (
    <fieldset
      aria-describedby={describedBy({ id: name, hint, error })}
      aria-invalid={error ? true : undefined}
      className={className}
      disabled={disabled}
    >
      <legend className="text-sm font-semibold text-ink">{legend}</legend>
      <FieldHint id={name}>{hint}</FieldHint>
      <div className="mt-1">
        {options.map((option) => {
          const id = `${name}-${option.value}`;
          return (
            <label className={choiceRow} htmlFor={id} key={option.value}>
              <input
                checked={
                  value === undefined ? undefined : value === option.value
                }
                className={box}
                defaultChecked={
                  defaultValue === undefined
                    ? undefined
                    : defaultValue === option.value
                }
                disabled={option.disabled}
                id={id}
                name={name}
                onChange={onChange ? () => onChange(option.value) : undefined}
                type="radio"
                value={option.value}
              />
              <span>{option.label}</span>
            </label>
          );
        })}
      </div>
      <FieldError id={name}>{error}</FieldError>
    </fieldset>
  );
}
