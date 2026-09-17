export interface OverviewEntryPoint {
  name: string;
  type: string;
  path: string;
  start_line: number;
  end_line: number;
  description: string;
  confidence: "confirmed" | "candidate" | "uncertain";
  evidence_ids: string[];
}

export interface OverviewComponent {
  id: string;
  name: string;
  type: string;
  description: string;
  paths: string[];
  responsibilities: string[];
  dependencies: string[];
  evidence_ids: string[];
}

export interface OverviewDataFlow {
  source: string;
  target: string;
  description: string;
  evidence_ids: string[];
}

export interface OverviewBoundary {
  name: string;
  description: string;
  paths: string[];
  evidence_ids: string[];
}

export interface OverviewDependency {
  name: string;
  purpose: string;
  evidence_ids: string[];
}

export interface OverviewConfigArea {
  path: string;
  description: string;
  evidence_ids: string[];
}

export interface OverviewUncertainty {
  statement: string;
  reason: string;
}

export interface OverviewDetail {
  summary: string;
  architecture_style: string | null;
  entry_points: OverviewEntryPoint[];
  components: OverviewComponent[];
  data_flows: OverviewDataFlow[];
  boundaries: OverviewBoundary[];
  key_dependencies: OverviewDependency[];
  configuration_areas: OverviewConfigArea[];
  uncertainties: OverviewUncertainty[];
}

export interface OverviewEvidenceRef {
  id: string;
  path: string;
  start_line: number;
  end_line: number;
  source_tool: string;
  redacted: boolean;
}

export interface RepositoryOverview {
  repository_id: string;
  snapshot_id: string;
  snapshot_active: boolean;
  overview_id: string;
  generated_at: string;
  generation_model: string;
  generation_status: string;
  stale: boolean;
  overview: OverviewDetail;
  evidence: OverviewEvidenceRef[];
  truncated: boolean;
  evidence_items_total: number;
  evidence_items_used: number;
}
