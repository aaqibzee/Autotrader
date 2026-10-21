"use client";

import { type RefObject, useMemo, useRef } from "react";
import { VisuallyHidden, mergeProps, useFocusRing, useSlider, useSliderThumb } from "react-aria";
import { type SliderState, useSliderState } from "react-stately";
import { cx } from "./cx";

/**
 * Two-thumb range, e.g. price and mileage filters (Feature 03 §2).
 *
 * Built from React Aria's hooks, not its `Slider` component, for two reasons:
 * - **Value text through `lib/format`.** The component formats `aria-valuetext` with an
 *   `Intl.NumberFormat` from `formatOptions`, so a value in pence would be read as
 *   "500,000" rather than "£5,000". Here the formatter is the caller's `formatValue`
 *   (`formatPrice`, `formatMileage`), the same function every other price on the page uses.
 * - **A documented page size.** React Aria moves `PageUp`/`PageDown` by a tenth of the
 *   range; here it is always ten steps.
 *
 * Values are integers in the caller's unit (pence, miles). The thumbs cannot cross: each
 * thumb's range stops at the other thumb.
 */
export type SliderRange = [number, number];

export type RangeSliderProps = {
  label: string;
  /** Names each thumb for screen readers, after the slider label: "Price, minimum". */
  thumbLabels: readonly [string, string];
  minValue: number;
  maxValue: number;
  step: number;
  value?: SliderRange;
  defaultValue?: SliderRange;
  onChange?: (value: SliderRange) => void;
  /** Fires once when a drag or key press ends; the place to update the URL. */
  onChangeEnd?: (value: SliderRange) => void;
  formatValue: (value: number) => string;
  /** Form field names for the two values. */
  names?: readonly [string, string];
  isDisabled?: boolean;
  className?: string;
};

export const PAGE_STEPS = 10;

/**
 * React Aria's state takes an `Intl.NumberFormat`. Subclassing keeps the type honest while
 * routing every label through our formatter; `resolvedOptions()` still reports en-GB.
 */
class FormatValueAdapter extends Intl.NumberFormat {
  readonly #formatValue: (value: number) => string;

  constructor(formatValue: (value: number) => string) {
    super("en-GB");
    this.#formatValue = formatValue;
  }

  override format(value: number | bigint): string {
    return this.#formatValue(Number(value));
  }

  override formatRange(start: number | bigint, end: number | bigint): string {
    return `${this.format(start)} – ${this.format(end)}`;
  }
}

const asRange = (values: number[]): SliderRange => [values[0] ?? 0, values[1] ?? 0];

export function RangeSlider({
  label,
  thumbLabels,
  minValue,
  maxValue,
  step,
  value,
  defaultValue,
  onChange,
  onChangeEnd,
  formatValue,
  names,
  isDisabled,
  className,
}: RangeSliderProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const numberFormatter = useMemo(() => new FormatValueAdapter(formatValue), [formatValue]);
  const ariaProps = {
    label,
    minValue,
    maxValue,
    step,
    value,
    defaultValue: defaultValue ?? [minValue, maxValue],
    isDisabled,
    onChange: onChange && ((values: number | number[]) => onChange(asRange([values].flat()))),
    onChangeEnd: onChangeEnd && ((values: number | number[]) => onChangeEnd(asRange([values].flat()))),
  };
  const baseState = useSliderState({ ...ariaProps, numberFormatter });
  const state: SliderState = { ...baseState, pageSize: step * PAGE_STEPS };
  const { groupProps, trackProps, labelProps, outputProps } = useSlider(ariaProps, state, trackRef);

  const low = state.getThumbPercent(0) * 100;
  const high = state.getThumbPercent(1) * 100;

  return (
    <div {...groupProps} className={cx("w-full", className)}>
      <div className="flex items-baseline justify-between gap-4">
        <label {...labelProps} className="text-sm font-semibold text-ink">
          {label}
        </label>
        <output {...outputProps} className="text-sm text-ink-soft tabular-nums">
          {state.getFormattedValue(state.values[0] ?? minValue)} – {state.getFormattedValue(state.values[1] ?? maxValue)}
        </output>
      </div>
      {/* 44px tall, so the whole track is a touch target; the visible bar is 4px. */}
      <div
        {...trackProps}
        className={cx("relative h-11 w-full", isDisabled ? "opacity-50" : "cursor-pointer")}
        ref={trackRef}
      >
        <div className="absolute top-1/2 h-1 w-full -translate-y-1/2 rounded-full bg-line" />
        {/* Positioned by style attributes, allowed by style-src-attr (Feature 03 A2). */}
        <div
          className="absolute top-1/2 h-1 -translate-y-1/2 rounded-full bg-brand"
          style={{ left: `${low}%`, width: `${high - low}%` }}
        />
        <Thumb index={0} label={thumbLabels[0]} name={names?.[0]} state={state} trackRef={trackRef} />
        <Thumb index={1} label={thumbLabels[1]} name={names?.[1]} state={state} trackRef={trackRef} />
      </div>
    </div>
  );
}

function Thumb({
  state,
  trackRef,
  index,
  label,
  name,
}: {
  state: SliderState;
  trackRef: RefObject<HTMLDivElement | null>;
  index: number;
  label: string;
  name?: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const { thumbProps, inputProps, isDragging } = useSliderThumb(
    { index, trackRef, inputRef, name, "aria-label": label },
    state,
  );
  const { focusProps, isFocusVisible } = useFocusRing();
  return (
    <div
      {...thumbProps}
      className={cx(
        "top-1/2 size-6 rounded-full border-2 border-brand bg-surface shadow-card",
        isDragging && "bg-brand-tint",
        isFocusVisible && "outline-2 outline-offset-2 outline-focus",
      )}
      // The thumb is the touch target; its range input is visually hidden (1px). The
      // gallery's 24px target check measures this instead.
      data-slider-thumb=""
    >
      <VisuallyHidden>
        <input ref={inputRef} {...mergeProps(inputProps, focusProps)} />
      </VisuallyHidden>
    </div>
  );
}
