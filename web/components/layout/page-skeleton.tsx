import { Skeleton } from "@/components/ui/display";

/**
 * What a route shows while its server component streams (Feature 03 §4): the page's
 * rough shape, never a bare spinner. `aria-busy` plus one status line for screen readers.
 */
export function PageSkeleton({ label = "Loading" }: { label?: string }) {
  return (
    <div aria-busy="true" className="shell py-10" data-page-skeleton="">
      <p className="sr-only" role="status">
        {label}…
      </p>
      <Skeleton className="h-9 w-2/3 max-w-md" />
      <Skeleton className="mt-4 h-4 w-full max-w-xl" />
      <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Skeleton className="h-56" />
        <Skeleton className="h-56" />
        <Skeleton className="h-56" />
      </div>
    </div>
  );
}
