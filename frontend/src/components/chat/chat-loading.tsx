import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent } from "@/components/ui/card";

export function ChatLoadingSkeleton() {
  return (
    <div className="space-y-4 px-4">
      <div className="flex gap-3">
        <Skeleton className="h-7 w-7 rounded-full" />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      </div>
      <Card className="border-dashed">
        <CardContent className="p-4 space-y-2">
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-4/5" />
          <Skeleton className="h-3 w-2/3" />
        </CardContent>
      </Card>
    </div>
  );
}
