export const EMBEDDING_NOT_CONFIGURED = "EMBEDDING_NOT_CONFIGURED";
export const EMBEDDING_AUTH_FAILED = "EMBEDDING_AUTH_FAILED";
export const EMBEDDING_PROVIDER_UNAVAILABLE = "EMBEDDING_PROVIDER_UNAVAILABLE";
export const EMBEDDING_PROVIDER_ERROR = "EMBEDDING_PROVIDER_ERROR";

export type IndexingFailureKind =
  | "not_configured"
  | "stale_not_configured"
  | "auth_failed"
  | "provider_unreachable"
  | "generic";

export function parseErrorCode(errorMessage?: string | null): string | null {
  if (!errorMessage) return null;
  const match = /^\[([A-Z][A-Z0-9_]*)\]/.exec(errorMessage.trim());
  return match ? match[1] : null;
}

export function stripErrorCode(errorMessage: string): string {
  return errorMessage.replace(/^\[[A-Z][A-Z0-9_]*\]\s*/, "");
}

export function classifyIndexingFailure(
  errorMessage?: string | null,
  providerConfigured?: boolean | null,
): IndexingFailureKind | null {
  const code = parseErrorCode(errorMessage);
  if (code === EMBEDDING_NOT_CONFIGURED) {
    // A stored failure predates the current backend config when the
    // diagnostics probe already reports a configured provider.
    if (providerConfigured === true) return "stale_not_configured";
    return "not_configured";
  }
  if (code === EMBEDDING_AUTH_FAILED) return "auth_failed";
  if (
    code === EMBEDDING_PROVIDER_UNAVAILABLE ||
    code === EMBEDDING_PROVIDER_ERROR
  ) {
    return "provider_unreachable";
  }
  if (!errorMessage) return null;
  return "generic";
}

export function isRetryEnabled(
  kind: IndexingFailureKind | null,
  providerConfigured?: boolean | null,
  retryBusy = false,
): boolean {
  if (retryBusy) return false;
  if (kind === "not_configured") return providerConfigured === true;
  return true;
}
