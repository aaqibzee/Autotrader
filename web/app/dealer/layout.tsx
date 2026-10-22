import { DealerChrome } from "@/components/layout/dealer-chrome";

// Signed-in surface (Feature 03 §6): always rendered per request, never cached or indexed.
// Middleware sets `Cache-Control: private, no-store` and `X-Robots-Tag: noindex` here.
export const dynamic = "force-dynamic";

// Feature 04 passes `dealerName` and `dealerStatus` from its dealer context (A8).
export default function DealerLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <DealerChrome>{children}</DealerChrome>;
}
