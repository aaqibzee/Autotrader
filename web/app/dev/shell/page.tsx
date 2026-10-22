import { PublicChrome } from "@/components/layout/public-chrome";
import { galleryEnabled } from "@/lib/dev/gallery";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { DevAccountIsland } from "./dev-account-island";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Shell probe",
  robots: { index: false },
};

/**
 * The public chrome with a signed-in account that arrives late (`?delay=1500`), for the
 * layout-shift test (Feature 03 slice 3.11). Dev only (A3).
 */
export default function ShellProbePage() {
  if (!galleryEnabled()) notFound();
  return (
    <PublicChrome
      account={<DevAccountIsland />}
      makeLinks={<p>Make links (Feature 13)</p>}
      showValuation
    >
      <div className="shell py-10">
        <h1 className="text-3xl font-semibold tracking-tight">Shell probe</h1>
        <p className="mt-3 max-w-prose text-ink-soft">
          The account slot below the header loads after the page. Its box is
          reserved, so nothing moves when it fills in.
        </p>
      </div>
    </PublicChrome>
  );
}
