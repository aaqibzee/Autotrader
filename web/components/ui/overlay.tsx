"use client";

import type { ReactNode } from "react";
import {
  Button as AriaButton,
  type ButtonProps as AriaButtonProps,
  Dialog,
  DialogTrigger,
  Heading,
  Modal as AriaModal,
  ModalOverlay,
} from "react-aria-components";
import { type ButtonSize, type ButtonVariant, buttonClasses } from "./button";
import { cx } from "./cx";

/**
 * Modal dialogs and the filter sheet (Feature 03 §2), on React Aria: focus moves into the
 * dialog, stays trapped there, returns to the trigger on close; `Escape` and a scrim
 * click close it; page scroll is locked. Animations are CSS only (CSP) and off under
 * reduced motion.
 */
export { DialogTrigger };

/**
 * The button that opens an overlay. React Aria's `DialogTrigger` only listens to React
 * Aria pressables, so this is its Button styled exactly like ours.
 */
export function TriggerButton({
  variant = "secondary",
  size = "md",
  className,
  ...rest
}: Omit<AriaButtonProps, "className"> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  className?: string;
}) {
  return (
    <AriaButton {...rest} className={buttonClasses(variant, size, className)} />
  );
}

type OverlayProps = {
  title: string;
  /** Visually hide the title (it still names the dialog for screen readers). */
  hideTitle?: boolean;
  children: ReactNode | ((close: () => void) => ReactNode);
  /** Shown in the footer, e.g. the primary action; gets the close function. */
  footer?: (close: () => void) => ReactNode;
  /** `false` for dialogs that must not be dismissed by a stray tap (unsaved work). */
  isDismissable?: boolean;
  className?: string;
};

const scrim = cx(
  "fixed inset-0 z-modal bg-ink/50",
  "data-entering:animate-[overlay-fade_150ms_ease-out] data-exiting:animate-[overlay-fade_120ms_ease-in_reverse]",
);

function DialogBody({ title, hideTitle, children, footer }: OverlayProps) {
  return (
    <Dialog className="flex max-h-[inherit] flex-col outline-none">
      {({ close }) => (
        <>
          <div className="flex items-center justify-between gap-4 border-b border-line px-5 py-3">
            <Heading
              className={cx("text-lg font-semibold", hideTitle && "sr-only")}
              slot="title"
            >
              {title}
            </Heading>
            <AriaButton
              aria-label="Close"
              className="-mr-2 ml-auto inline-flex size-11 items-center justify-center rounded-md text-ink hover-state:bg-sunken"
              slot="close"
            >
              <svg
                aria-hidden="true"
                className="size-5"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                viewBox="0 0 24 24"
              >
                <path d="M6 6l12 12M18 6L6 18" />
              </svg>
            </AriaButton>
          </div>
          <div className="flex-1 overflow-y-auto px-5 py-4">
            {typeof children === "function" ? children(close) : children}
          </div>
          {footer && (
            <div className="border-t border-line px-5 py-3">
              {footer(close)}
            </div>
          )}
        </>
      )}
    </Dialog>
  );
}

/** Centred dialog: confirmations, the stale-update conflict dialog (slice 3.10). */
export function Modal(props: OverlayProps) {
  return (
    <ModalOverlay
      className={cx(scrim, "flex items-center justify-center p-4")}
      isDismissable={props.isDismissable ?? true}
    >
      <AriaModal
        className={cx(
          "max-h-[90dvh] w-full max-w-lg rounded-lg bg-surface text-ink shadow-overlay",
          "data-entering:animate-[modal-in_150ms_ease-out] data-exiting:animate-[modal-in_120ms_ease-in_reverse]",
          props.className,
        )}
      >
        <DialogBody {...props} />
      </AriaModal>
    </ModalOverlay>
  );
}

/**
 * Bottom sheet on phones, side panel from `lg` (Feature 03 §1: the filter sheet becomes a
 * sidebar at `lg`). Full height on a phone is capped at 85% so the page stays visible.
 */
export function Sheet(props: OverlayProps) {
  return (
    <ModalOverlay className={scrim} isDismissable={props.isDismissable ?? true}>
      <AriaModal
        className={cx(
          "fixed inset-x-0 bottom-0 z-sheet max-h-[85dvh] rounded-t-xl bg-surface text-ink shadow-overlay",
          "lg:inset-y-0 lg:right-0 lg:left-auto lg:max-h-none lg:w-96 lg:rounded-none",
          "data-entering:animate-[sheet-up_200ms_ease-out] data-exiting:animate-[sheet-up_150ms_ease-in_reverse]",
          "lg:data-entering:animate-[sheet-left_200ms_ease-out] lg:data-exiting:animate-[sheet-left_150ms_ease-in_reverse]",
          props.className,
        )}
      >
        <DialogBody {...props} />
      </AriaModal>
    </ModalOverlay>
  );
}
