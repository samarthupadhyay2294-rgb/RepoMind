import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import type { RepositoryStatus } from "@/lib/types";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Loader2,
  XCircle,
} from "lucide-react";

const statusConfig: Record<
  RepositoryStatus,
  { label: string; variant: "default" | "secondary" | "destructive" | "outline"; icon: React.ComponentType<{ className?: string }> }
> = {
  ready: { label: "Ready", variant: "default", icon: CheckCircle2 },
  indexed: { label: "Ready", variant: "default", icon: CheckCircle2 },
  indexing: { label: "Indexing", variant: "secondary", icon: Loader2 },
  pending: { label: "Pending", variant: "outline", icon: Clock },
  failed: { label: "Failed", variant: "destructive", icon: XCircle },
  deleted: { label: "Deleted", variant: "destructive", icon: AlertCircle },
};

export function RepositoryStatusBadge({
  status,
  className,
}: {
  status: RepositoryStatus;
  className?: string;
}) {
  const config = statusConfig[status] ?? statusConfig.pending;
  const Icon = config.icon;

  return (
    <Badge variant={config.variant} className={cn("gap-1", className)}>
      <Icon
        className={cn(
          "h-3 w-3",
          status === "indexing" && "animate-spin",
        )}
      />
      {config.label}
    </Badge>
  );
}
