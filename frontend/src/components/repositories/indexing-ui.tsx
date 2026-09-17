"use client";

import {
  AlertCircle,
  Loader2,
  RotateCcw,
  Settings,
  TriangleAlert,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import type { RepositoryStatus } from "@/lib/types";
import {
  classifyIndexingFailure,
  isRetryEnabled,
  stripErrorCode,
  type IndexingFailureKind,
} from "@/lib/indexing-error-state";

interface IndexingUIProps {
  status: RepositoryStatus;
  errorMessage?: string | null;
  onRetry?: () => void;
  providerConfigured?: boolean | null;
  retryBusy?: boolean;
}

const KIND_COPY: Record<
  IndexingFailureKind,
  { title: string; body: string; retryLabel: string }
> = {
  not_configured: {
    title: "Indexing needs an embedding provider",
    body: "Indexing needs an embedding provider before RepoMind can search your code.",
    retryLabel: "Configure provider, then restart backend",
  },
  stale_not_configured: {
    title: "Backend is now configured — retry indexing",
    body: "This failure was recorded before the embedding provider was configured. The backend now reports a configured provider, so retrying should proceed.",
    retryLabel: "Retry indexing",
  },
  auth_failed: {
    title: "Embedding provider rejected the API key",
    body: "The backend is configured, but Mistral rejected the API key. Check MISTRAL_API_KEY in backend/.env, then restart the backend.",
    retryLabel: "Retry indexing",
  },
  provider_unreachable: {
    title: "Embedding provider request failed",
    body: "The backend is configured, but the Mistral request failed (network or provider error). Wait briefly, then retry.",
    retryLabel: "Retry indexing",
  },
  generic: {
    title: "Indexing failed",
    body: "We could not finish indexing this repository.",
    retryLabel: "Retry indexing",
  },
};

export function IndexingUI({
  status,
  errorMessage,
  onRetry,
  providerConfigured = null,
  retryBusy = false,
}: IndexingUIProps) {
  if (status === "ready" || status === "indexed") return null;

  if (status === "failed") {
    const kind =
      classifyIndexingFailure(errorMessage, providerConfigured) ?? "generic";
    const copy = KIND_COPY[kind];
    const technical = errorMessage ? stripErrorCode(errorMessage) : "";
    const retryEnabled =
      onRetry !== undefined &&
      isRetryEnabled(kind, providerConfigured, retryBusy);

    if (kind === "generic") {
      return (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Indexing failed</AlertTitle>
          <AlertDescription className="mt-1">
            <p className="mb-2">
              {errorMessage
                ? stripErrorCode(errorMessage)
                : "We could not finish indexing this repository."}
            </p>
            {onRetry && (
              <Button
                variant="outline"
                size="sm"
                onClick={onRetry}
                disabled={!retryEnabled}
              >
                <RotateCcw className="mr-2 h-3 w-3" />
                Retry indexing
              </Button>
            )}
          </AlertDescription>
        </Alert>
      );
    }

    const isConfigKind =
      kind === "not_configured" || kind === "stale_not_configured";
    return (
      <Alert variant="default" className="border-warning/30 bg-warning/10">
        {isConfigKind ? (
          <TriangleAlert className="h-4 w-4 text-warning" />
        ) : (
          <AlertCircle className="h-4 w-4" />
        )}
        <AlertTitle>{copy.title}</AlertTitle>
        <AlertDescription className="mt-1">
          <p className="mb-2">{copy.body}</p>
          {(kind === "not_configured" || kind === "auth_failed") && (
            <>
              <p className="mb-1">
                <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-foreground">
                  MISTRAL_API_KEY=your_key_here
                </code>
              </p>
              <p className="mb-2">
                Add this to{" "}
                <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-foreground">
                  backend/.env
                </code>
                , then restart the backend.
              </p>
            </>
          )}
          {onRetry &&
            (kind === "not_configured" && !retryEnabled ? (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  disabled
                  aria-describedby="embedding-config-retry-hint"
                >
                  <Settings className="mr-2 h-3 w-3" />
                  {copy.retryLabel}
                </Button>
                <p id="embedding-config-retry-hint" className="mt-2 text-xs">
                  Retry becomes available after the backend is restarted with a
                  configured provider.
                </p>
              </>
            ) : (
              <Button
                variant="outline"
                size="sm"
                onClick={onRetry}
                disabled={!retryEnabled}
              >
                <RotateCcw className="mr-2 h-3 w-3" />
                {copy.retryLabel}
              </Button>
            ))}
          {technical && (
            <details className="mt-2 text-xs">
              <summary className="cursor-pointer underline underline-offset-2">
                Technical details
              </summary>
              <p className="mt-1 font-mono">{technical}</p>
            </details>
          )}
        </AlertDescription>
      </Alert>
    );
  }

  if (status === "indexing") {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin" />
            Indexing repository
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Progress value={50} className="h-2">
            <span className="sr-only">Indexing in progress</span>
          </Progress>
          <p className="text-xs text-muted-foreground">
            Analyzing source files... This may take a few moments.
          </p>
        </CardContent>
      </Card>
    );
  }

  // pending
  return (
    <Card>
      <CardContent className="flex items-center gap-3 p-4">
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        <p className="text-sm text-muted-foreground">Waiting to start indexing...</p>
        <div className="flex-1" />
        {onRetry && (
          <Button variant="outline" size="sm" onClick={onRetry}>
            Start indexing
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
