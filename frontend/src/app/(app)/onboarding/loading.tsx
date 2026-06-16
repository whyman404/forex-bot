import { Skeleton } from "@/components/ui/skeleton";

export default function OnboardingLoading() {
  return (
    <div className="space-y-8">
      <Skeleton className="h-9 w-72" />
      <Skeleton className="h-16" />
      <Skeleton className="h-96" />
    </div>
  );
}
