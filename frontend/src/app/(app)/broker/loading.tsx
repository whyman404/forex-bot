import { Skeleton } from "@/components/ui/skeleton";

export default function BrokerLoading() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-9 w-48" />
      <Skeleton className="h-64" />
    </div>
  );
}
