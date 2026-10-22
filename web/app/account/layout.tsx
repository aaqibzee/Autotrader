import { PublicChrome } from "@/components/layout/public-chrome";

// Signed-in surface (Feature 03 §6): always rendered per request, never cached or indexed.
// Middleware sets `Cache-Control: private, no-store` and `X-Robots-Tag: noindex` here.
export const dynamic = "force-dynamic";

export default function AccountLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <PublicChrome>{children}</PublicChrome>;
}
