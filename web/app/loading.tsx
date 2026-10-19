export default function Loading() {
  return (
    <main aria-busy="true" className="shell flex min-h-screen items-center justify-center">
      <p aria-live="polite" className="font-mono text-sm text-[var(--muted)]" role="status">
        Checking service readiness...
      </p>
    </main>
  );
}