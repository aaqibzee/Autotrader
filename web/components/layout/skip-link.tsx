/** First focusable element on every page: jumps past the header (WCAG 2.4.1). */
export function SkipLink({ target = "main" }: { target?: string }) {
  return (
    <a
      className="sr-only z-toast rounded-md bg-surface px-4 py-3 font-semibold text-ink shadow-overlay focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      href={`#${target}`}
    >
      Skip to content
    </a>
  );
}
