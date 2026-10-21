// Signed-in surface (Feature 03 §6): always rendered per request, never cached or indexed.
// Middleware sets `Cache-Control: private, no-store` and `X-Robots-Tag: noindex` here.
export const dynamic = "force-dynamic";

export default function DealerLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
