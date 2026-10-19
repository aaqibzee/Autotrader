import { ApiError } from "@/lib/api/error";
import { getServerApi } from "@/lib/api/server";
import Link from "next/link";

export default async function HomePage() {
  let ready = false;
  let requestId: string | undefined;

  try {
    const readiness = await getServerApi("/api/v1/health/ready");
    ready = readiness.status === "ready";
  } catch (error) {
    if (error instanceof ApiError) {
      requestId = error.requestId;
    }
  }

  return (
    <main className="shell flex min-h-screen flex-col">
      <header className="flex items-center justify-between border-b border-[var(--line)] py-6">
        <Link aria-label="Autotrader home" className="text-lg font-black tracking-tight" href="/">
          AUTOTRADER<span className="text-[#71972a]">.</span>
        </Link>
        <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-[var(--muted)]">
          Platform foundation
        </span>
      </header>

      <section className="grid flex-1 content-center gap-12 py-16 md:grid-cols-[1.2fr_0.8fr] md:items-center">
        <div className="max-w-2xl">
          <p className="mb-5 font-mono text-xs uppercase tracking-[0.16em] text-[var(--muted)]">
            United Kingdom · Vehicle marketplace
          </p>
          <h1 className="text-5xl font-semibold leading-[0.98] tracking-tight sm:text-7xl">
            The road starts here.
          </h1>
          <p className="mt-6 max-w-lg text-base leading-7 text-[var(--muted)]">
            The web platform is in place. Marketplace experiences will arrive in the next build
            stages.
          </p>
        </div>

        <aside
          aria-live="polite"
          className="border border-[var(--line)] bg-[var(--surface)] p-6 shadow-[0_16px_50px_rgba(23,33,31,0.06)] sm:p-8"
        >
          <div className="flex items-center justify-between gap-4 border-b border-[var(--line)] pb-5">
            <h2 className="text-sm font-semibold">Service readiness</h2>
            <span
              className={`h-2.5 w-2.5 rounded-full ${ready ? "status-pulse bg-[#71972a]" : "bg-[#bd6a3d]"}`}
              aria-hidden="true"
            />
          </div>
          <p className="mt-6 font-mono text-xs uppercase tracking-[0.12em] text-[var(--muted)]">
            API
          </p>
          <p className="mt-1 text-3xl font-semibold tracking-tight">
            {ready ? "ready" : "unavailable"}
          </p>
          {!ready && (
            <p className="mt-3 text-sm leading-6 text-[var(--muted)]">
              The readiness endpoint did not respond. Start the API and refresh this page.
              {requestId && <span className="mt-2 block font-mono text-xs">Request ID: {requestId}</span>}
            </p>
          )}
        </aside>
      </section>

      <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--line)] py-5 font-mono text-[10px] uppercase tracking-[0.1em] text-[var(--muted)]">
        <span>Built for the UK market</span>
        <span>Foundation · 01</span>
      </footer>
    </main>
  );
}