export type SourceType = "local" | "git";

export type RepositoryStatus =
  | "pending"
  | "ready"
  | "indexing"
  | "indexed"
  | "failed"
  | "deleted";

export interface Repository {
  id: string;
  owner_id: string;
  name: string;
  source_type: SourceType;
  source_url: string | null;
  local_path: string | null;
  default_branch: string | null;
  current_commit_sha: string | null;
  status: RepositoryStatus;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface RepositoryCreate {
  name: string;
  source_type: SourceType;
  source_url?: string;
  local_path?: string;
  default_branch?: string;
}

export interface RepositoryUpdate {
  name?: string;
  source_url?: string;
  default_branch?: string;
}

export interface RepositoryListResponse {
  items: Repository[];
  total: number;
}

export interface ChatCitation {
  repository_id: string;
  file_path: string;
  start_line: number;
  end_line: number;
  source_type: string;
  reason: string;
}

export interface ChatMetrics {
  latency_ms: number;
  llm_calls: number;
  tool_calls: number;
  steps: number;
  prompt_tokens: number | null;
  completion_tokens: number | null;
}

export interface ChatResponse {
  answer: string;
  citations: ChatCitation[];
  steps_taken: string[];
  warnings: string[];
  request_type: string;
  session_id: string;
  metrics?: ChatMetrics | null;
}

export interface ChatRequest {
  repository_id: string;
  question: string;
  session_id?: string;
}

export interface ChatTraceResponse {
  session_id: string;
  repository_id: string;
  request_type: string;
  steps_taken: string[];
  warnings: string[];
  citations: ChatCitation[];
  answer: string;
}

export interface AppError {
  error: {
    code: string;
    message: string;
  };
}
