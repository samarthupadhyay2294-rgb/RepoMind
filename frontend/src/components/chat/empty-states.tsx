import { AlertCircle, Info } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

export function EmptyChatState() {
  return (
    <div className="flex flex-1 items-center justify-center p-8">
      <div className="max-w-md text-center space-y-3">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-muted">
          <Info className="h-6 w-6 text-muted-foreground" />
        </div>
        <h3 className="text-lg font-semibold">Ask about this repository</h3>
        <p className="text-sm text-muted-foreground">
          RepoMind will investigate your codebase and provide grounded answers
          backed by source citations.
        </p>
      </div>
    </div>
  );
}

export function InsufficientEvidenceState() {
  return (
    <Alert>
      <AlertCircle className="h-4 w-4" />
      <AlertTitle>Not enough repository evidence</AlertTitle>
      <AlertDescription className="mt-1">
        <p>
          I could not find enough relevant code to answer this confidently.
        </p>
        <p className="mt-1">
          Try asking about a specific file, symbol, or feature.
        </p>
      </AlertDescription>
    </Alert>
  );
}
