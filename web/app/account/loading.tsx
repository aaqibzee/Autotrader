import { PageSkeleton } from "@/components/layout/page-skeleton";

// Inside the layout, so the chrome stays put while the page streams (Feature 03 §4).
export default function Loading() {
  return <PageSkeleton />;
}
