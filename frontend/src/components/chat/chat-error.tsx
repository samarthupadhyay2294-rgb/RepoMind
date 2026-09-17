import { AlertCircle } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { RefreshCw } from "lucide-react";

interface ChatErrorProps {
  message: string;
  onRetry?: () => void;
}

export function ChatError({ message, onRetry }: ChatErrorProps) {
  return (
    <Alert variant="destructive">
      <AlertCircle className="h-4 w-4" />
      <AlertDescription className="flex items-center justify-between">
        <span>{message}</span>
        {onRetry && (
          <Button variant="outline" size="sm" onClick={onRetry}>
            <RefreshCw className="mr-2 h-3 w-3" />
            Retry
          </Button>
        )}
      </AlertDescription>
    </Alert>
  );
}
