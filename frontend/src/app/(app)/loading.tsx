import { Skeleton } from "@/components/ui/skeleton";

/**
 * Group loading state for the authenticated app shell. Shown during partial
 * prerender + on first navigation between (app) routes.
 */
export default function AppLoading() {
  return (
    <div className="space-y-4 p-4 md:p-6">
      <Skeleton className="h-8 w-64" />
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Skeleton className="h-32" />
        <Skeleton className="h-32" />
        <Skeleton className="h-32" />
        <Skeleton className="h-32" />
      </div>
      <Skeleton className="h-64" />
    </div>
  );
}
