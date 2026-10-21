import Link from "next/link";

export default function NotFound() {
  return (
    <main className="shell flex min-h-screen flex-col items-start justify-center">
      <p className="font-mono text-xs uppercase tracking-[0.14em] text-ink-muted">
        404
      </p>
      <h1 className="mt-3 text-4xl font-semibold tracking-tight">
        This road ends here.
      </h1>
      <Link
        className="mt-6 border border-ink px-4 py-2 text-sm font-semibold transition-colors hover:bg-ink hover:text-surface"
        href="/"
      >
        Back to start
      </Link>
    </main>
  );
}
