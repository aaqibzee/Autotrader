import { PageSkeleton } from "@/components/layout/page-skeleton";

// Outside any chrome (a route group without its own loading.tsx). Feature 03 §4.
export default function Loading() {
  return (
    <main id="main">
      <PageSkeleton />
    </main>
  );
}
