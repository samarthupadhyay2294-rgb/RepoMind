export interface GraphNode {
  id: string;
  type: string;
  name: string;
  qualified_name: string;
  path: string;
  start_line: number;
  end_line: number;
  signature?: string;
  language?: string | null;
  snapshot_id: string;
  provenance: string;
  parent_symbol_id?: string | null;
  metadata?: Record<string, unknown>;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  relationship_type: string;
  confidence: number;
  provenance: string;
  evidence: {
    path: string;
    start_line: number;
    end_line: number;
    excerpt: string;
  };
  metadata?: Record<string, unknown>;
}

export interface GraphNeighborhood {
  repository_id: string;
  snapshot_id: string;
  snapshot_active: boolean;
  root: string | null;
  nodes: GraphNode[];
  edges: GraphEdge[];
  truncated: boolean;
  limit_reason: string | null;
  limits: { max_nodes: number; max_edges: number; max_depth: number };
}

export interface GraphNodeDetail {
  node: GraphNode;
  relationships: GraphEdge[];
  evidence: Record<string, unknown>[];
}

export interface GraphEdgeDetail {
  edge: GraphEdge;
  source: GraphNode;
  target: GraphNode;
  evidence: Record<string, unknown>[];
}

export interface GraphExplainResponse {
  explanation: string;
  evidence: { path: string; start_line: number; end_line: number; excerpt?: string }[];
  confidence: string;
}
