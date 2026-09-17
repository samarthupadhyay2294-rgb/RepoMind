import type {
  ChatRequest,
  ChatResponse,
  ChatTraceResponse,
  Repository,
  RepositoryCreate,
  RepositoryListResponse,
  RepositoryUpdate,
} from "./types";
import type {
  GraphEdgeDetail,
  GraphExplainResponse,
  GraphNeighborhood,
  GraphNodeDetail,
} from "./graph-types";
import type { RepositoryOverview } from "./overview-types";
import type { ArchitectureMap, Investigation, InvestigationInput } from "./debug-types";

export interface ConfigDiagnostics {
  embedding_provider_configured: boolean;
  embedding_provider_name: string;
  embedding_model: string;
  embedding_config_source?: string;
  llm_provider: string;
  ollama_configured: boolean;
  qdrant_configured: boolean;
}

const DEFAULT_TIMEOUT_MS = 30000;

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number = 0,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface RequestOptions extends RequestInit {
  timeoutMs?: number;
}

async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...fetchOptions } = options;
  const url = `${API_BASE}${path}`;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  if (options.signal) {
    options.signal.addEventListener("abort", () => controller.abort(), { once: true });
  }

  let res: Response;
  try {
    res = await fetch(url, {
      ...fetchOptions,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...fetchOptions.headers,
      },
    });
  } catch (err: unknown) {
    clearTimeout(timeoutId);
    if (controller.signal.aborted && (!options.signal || !options.signal.aborted)) {
      throw new ApiError(
        "REQUEST_TIMEOUT",
        "Request timed out. The backend server took too long to respond.",
        408,
      );
    }
    if (err instanceof ApiError) throw err;
    throw new ApiError(
      "BACKEND_UNREACHABLE",
      "Unable to connect to the backend server. Please check if the backend is running.",
      0,
    );
  } finally {
    clearTimeout(timeoutId);
  }

  if (res.status === 204) return undefined as T;

  let body: unknown;
  try {
    body = await res.json();
  } catch {
    if (!res.ok) {
      throw new ApiError(
        "SERVER_ERROR",
        `Request failed with status ${res.status}. Please check if the backend server is running.`,
        res.status,
      );
    }
    return undefined as T;
  }

  if (!res.ok) {
    const errObj = body as { error?: { message?: string; code?: string }; detail?: string } | null;
    const rawMsg = errObj?.error?.message ?? errObj?.detail ?? `Request failed (${res.status})`;
    const msg = typeof rawMsg === "string" ? rawMsg.split("\n")[0] : `Request failed (${res.status})`;
    const code = errObj?.error?.code ?? (res.status >= 500 ? "SERVER_ERROR" : "API_ERROR");
    throw new ApiError(code, msg, res.status);
  }

  return body as T;
}

// ── Repositories ──────────────────────────────────────────────

export async function listRepositories(
  limit = 50,
  offset = 0,
  options: RequestOptions = {},
): Promise<RepositoryListResponse> {
  return request(`/api/v1/repositories?limit=${limit}&offset=${offset}`, options);
}

export async function getRepository(id: string): Promise<Repository> {
  return request(`/api/v1/repositories/${id}`);
}

export async function createRepository(
  data: RepositoryCreate,
): Promise<Repository> {
  return request("/api/v1/repositories", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateRepository(
  id: string,
  data: RepositoryUpdate,
): Promise<Repository> {
  return request(`/api/v1/repositories/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deleteRepository(id: string): Promise<void> {
  return request(`/api/v1/repositories/${id}`, {
    method: "DELETE",
  });
}

export async function startIndexing(id: string): Promise<Repository> {
  return request(`/api/v1/repositories/${id}/index`, {
    method: "POST",
  });
}

// ── Chat ──────────────────────────────────────────────────────

export async function sendChatMessage(
  data: ChatRequest,
): Promise<ChatResponse> {
  return request("/api/v1/chat", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function getChatTrace(
  sessionId: string,
  repositoryId: string,
): Promise<ChatTraceResponse> {
  return request(
    `/api/v1/chat/${sessionId}?repository_id=${encodeURIComponent(repositoryId)}`,
  );
}

// ── Graph (Part 2) ────────────────────────────────────────────

export interface GraphQuery {
  snapshot_id?: string;
  node_id?: string;
  depth?: number;
  direction?: string;
  relationship_types?: string;
  node_types?: string;
  limit?: number;
}

export function graphQueryString(q: GraphQuery): string {
  const params = new URLSearchParams();
  if (q.snapshot_id) params.set("snapshot_id", q.snapshot_id);
  if (q.node_id) params.set("node_id", q.node_id);
  if (q.depth !== undefined) params.set("depth", String(q.depth));
  if (q.direction) params.set("direction", q.direction);
  if (q.relationship_types) params.set("relationship_types", q.relationship_types);
  if (q.node_types) params.set("node_types", q.node_types);
  if (q.limit !== undefined) params.set("limit", String(q.limit));
  const s = params.toString();
  return s ? `?${s}` : "";
}

export async function getGraph(
  repositoryId: string,
  query: GraphQuery = {},
): Promise<GraphNeighborhood> {
  return request(`/api/v1/repositories/${repositoryId}/graph${graphQueryString(query)}`);
}

export async function getGraphNode(
  repositoryId: string,
  nodeId: string,
  snapshotId?: string,
): Promise<GraphNodeDetail> {
  const suffix = snapshotId ? `?snapshot_id=${encodeURIComponent(snapshotId)}` : "";
  return request(`/api/v1/repositories/${repositoryId}/graph/nodes/${nodeId}${suffix}`);
}

export async function getGraphEdge(
  repositoryId: string,
  edgeId: string,
  snapshotId?: string,
): Promise<GraphEdgeDetail> {
  const suffix = snapshotId ? `?snapshot_id=${encodeURIComponent(snapshotId)}` : "";
  return request(`/api/v1/repositories/${repositoryId}/graph/edges/${edgeId}${suffix}`);
}

export async function explainGraph(
  repositoryId: string,
  body: { node_id?: string; edge_id?: string; question?: string },
  snapshotId?: string,
): Promise<GraphExplainResponse> {
  const suffix = snapshotId ? `?snapshot_id=${encodeURIComponent(snapshotId)}` : "";
  return request(`/api/v1/repositories/${repositoryId}/graph/explain${suffix}`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// ── Overview (Part 3) ─────────────────────────────────────────

export async function getOverview(
  repositoryId: string,
  snapshotId?: string,
): Promise<RepositoryOverview> {
  const suffix = snapshotId ? `?snapshot_id=${encodeURIComponent(snapshotId)}` : "";
  return request(`/api/v1/repositories/${repositoryId}/overview${suffix}`);
}

export async function generateOverview(
  repositoryId: string,
  snapshotId?: string,
): Promise<RepositoryOverview> {
  return request(`/api/v1/repositories/${repositoryId}/overview:generate`, {
    method: "POST",
    body: JSON.stringify(snapshotId ? { snapshot_id: snapshotId } : {}),
  });
}

// ── Debug investigator (Part 4) ───────────────────────────────

export async function createInvestigation(
  repositoryId: string,
  input: InvestigationInput,
): Promise<Investigation> {
  return request(`/api/v1/repositories/${repositoryId}/investigations`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function getInvestigation(
  repositoryId: string,
  runId: string,
): Promise<Investigation> {
  return request(`/api/v1/repositories/${repositoryId}/investigations/${runId}`);
}

export async function getArchitectureMap(
  repositoryId: string,
  snapshotId?: string,
): Promise<ArchitectureMap> {
  const suffix = snapshotId ? `?snapshot_id=${encodeURIComponent(snapshotId)}` : "";
  return request(`/api/v1/repositories/${repositoryId}/architecture${suffix}`);
}

// ── Configuration Diagnostics ───────────────────────────────────

export async function getConfigDiagnostics(): Promise<ConfigDiagnostics> {
  return request("/api/v1/config/diagnostics");
}

// ── Health ────────────────────────────────────────────────────

export async function checkHealth(): Promise<{ status: string }> {
  return request("/health");
}
