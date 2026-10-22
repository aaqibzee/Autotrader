import { PublicChrome } from "@/components/layout/public-chrome";

// Feature 03 §5. Feature 12 passes `showValuation`, Feature 13 `makeLinks`, Feature 04
// the account loader (A8).
export default function PublicLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <PublicChrome>{children}</PublicChrome>;
}
