export interface InvestigationInput {
  error_text: string;
  stack_trace?: string;
  affected_route?: string;
  environment?: string;
  expected_behavior?: string;
  actual_behavior?: string;
  reproduction_steps?: string;
  snapshot_id?: string;
}

export interface InvestigationAction {
  sequence: number;
  tool: string;
  ok: boolean;
  result_count: number;
  warning: string;
  duration_ms: number;
}

export interface Investigation {
  id: string;
  repository_id: string;
  snapshot_id: string;
  snapshot_active: boolean;
  status: "pending" | "running" | "completed" | "failed";
  verdict: "confirmed" | "likely" | "unresolved" | null;
  confidence: string | null;
  summary: string;
  findings: { claim: string; confidence: string; evidence_refs: string[] }[];
  next_steps: string[];
  limitations: string[];
  citations: {
    repository_id: string;
    file_path: string;
    start_line: number;
    end_line: number;
    source_type: string;
    reason: string;
  }[];
  actions: InvestigationAction[];
  stop_reason: string;
  tool_calls: number;
  llm_calls: number;
  duration_ms: number;
  evidence_truncated: boolean;
  session_id: string | null;
  created_at: string;
}

export interface ArchitectureMap {
  repository_id: string;
  snapshot_id: string;
  snapshot_active: boolean;
  components: {
    id: string;
    name: string;
    type: string;
    description: string;
    paths: string[];
    responsibilities: string[];
    dependencies: string[];
    evidence_ids: string[];
  }[];
  data_flows: { source: string; target: string; description: string; evidence_ids: string[] }[];
  entry_points: {
    name: string;
    type: string;
    path: string;
    start_line: number;
    end_line: number;
    description: string;
    confidence: string;
    evidence_ids: string[];
  }[];
}
