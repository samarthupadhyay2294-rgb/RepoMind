"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/layout/app-shell";
import { Button } from "@/components/ui/button";
import {
  ApiError,
  explainGraph,
  getGraph,
  getGraphEdge,
  getGraphNode,
  getRepository,
} from "@/lib/api";
import type {
  GraphEdge,
  GraphExplainResponse,
  GraphNeighborhood,
  GraphNode,
} from "@/lib/graph-types";
import type { Repository } from "@/lib/types";

import { GraphToolbar } from "@/components/graph/graph-toolbar";
import { GraphCanvas } from "@/components/graph/graph-canvas";
import { GraphInspector } from "@/components/graph/graph-inspector";
import { GraphOverview } from "@/components/graph/graph-overview";
import { GraphLegend } from "@/components/graph/graph-legend";
import { GraphTextAlternative } from "@/components/graph/graph-text-alternative";
import { GitBranch, AlertCircle, RefreshCw, CheckCircle2 } from "lucide-react";

export default function GraphPage() {
  const params = useParams();
  const router = useRouter();
  const search = useSearchParams();
  const id = params.id as string;

  const urlNode = search.get("node");
  const urlDepth = Number(search.get("depth") ?? "2");

  const [repo, setRepo] = useState<Repository | null>(null);
  const [data, setData] = useState<GraphNeighborhood | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [disabled, setDisabled] = useState(false);

  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(urlNode);

  const [relFilter, setRelFilter] = useState<string[]>([]);
  const [nodeFilter, setNodeFilter] = useState<string[]>([]);
  const [depth, setDepth] = useState(
    Number.isFinite(urlDepth) ? Math.min(Math.max(urlDepth, 1), 3) : 2,
  );
  const [searchQuery, setSearchQuery] = useState("");
  const [showLabels, setShowLabels] = useState(false);

  const [explanation, setExplanation] = useState<GraphExplainResponse | null>(null);
  const [explaining, setExplaining] = useState(false);
  const [fitViewTrigger, setFitViewTrigger] = useState(0);

  // Sync state to URL params
  const updateUrlParams = useCallback(
    (nodeId: string | null, newDepth: number) => {
      const p = new URLSearchParams(search.toString());
      if (nodeId) p.set("node", nodeId);
      else p.delete("node");
      p.set("depth", String(newDepth));
      router.replace(`/repositories/${id}/graph?${p.toString()}`);
    },
    [id, router, search],
  );

  // Load repo metadata
  useEffect(() => {
    getRepository(id)
      .then(setRepo)
      .catch(() => {});
  }, [id]);

  // Load graph data from API
  useEffect(() => {
    let cancelled = false;
    async function fetchGraph() {
      setLoading(true);
      setError(null);
      setDisabled(false);
      try {
        const g = await getGraph(id, {
          node_id: urlNode ?? undefined,
          depth,
          relationship_types: relFilter.length ? relFilter.join(",") : undefined,
          node_types: nodeFilter.length ? nodeFilter.join(",") : undefined,
        });
        if (!cancelled) {
          setData(g);
          if (urlNode) {
            const found = g.nodes.find((n) => n.id === urlNode);
            if (found) {
              setSelectedNode(found);
              setFocusedNodeId(found.id);
            }
          }
        }
      } catch (err: unknown) {
        if (cancelled) return;
        if (err instanceof ApiError && err.code === "GRAPH_DISABLED") {
          setDisabled(true);
        } else {
          setError(err instanceof Error ? err.message : "Failed to load dependency graph.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    fetchGraph();
    return () => {
      cancelled = true;
    };
  }, [id, urlNode, depth, relFilter, nodeFilter]);

  const nodeById = useMemo(() => {
    const map = new Map<string, GraphNode>();
    data?.nodes.forEach((n) => map.set(n.id, n));
    if (selectedNode && !map.has(selectedNode.id)) {
      map.set(selectedNode.id, selectedNode);
    }
    return map;
  }, [data, selectedNode]);

  const { incomingEdges, outgoingEdges } = useMemo(() => {
    if (!selectedNode || !data) return { incomingEdges: [], outgoingEdges: [] };
    const inc: GraphEdge[] = [];
    const out: GraphEdge[] = [];
    data.edges.forEach((e) => {
      if (e.target === selectedNode.id) inc.push(e);
      if (e.source === selectedNode.id) out.push(e);
    });
    return { incomingEdges: inc, outgoingEdges: out };
  }, [selectedNode, data]);

  const handleSelectNode = useCallback(
    async (node: GraphNode | null) => {
      if (!node) {
        setSelectedNode(null);
        setExplanation(null);
        updateUrlParams(null, depth);
        return;
      }

      setSelectedNode(node);
      setSelectedEdge(null);
      setExplanation(null);
      setFocusedNodeId(node.id);
      updateUrlParams(node.id, depth);

      try {
        const detail = await getGraphNode(id, node.id, data?.snapshot_id);
        setSelectedNode(detail.node);

        const g = await getGraph(id, { node_id: node.id, depth: 1 });
        setData((prev) => {
          if (!prev) return g;
          const nodeMap = new Map(prev.nodes.map((n) => [n.id, n]));
          g.nodes.forEach((n) => nodeMap.set(n.id, n));
          const edgeMap = new Map(prev.edges.map((e) => [e.id, e]));
          g.edges.forEach((e) => edgeMap.set(e.id, e));
          return {
            ...prev,
            nodes: Array.from(nodeMap.values()),
            edges: Array.from(edgeMap.values()),
          };
        });
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "Failed to expand node details.");
      }
    },
    [id, data, depth, updateUrlParams],
  );

  const handleSelectEdge = useCallback(
    async (edge: GraphEdge | null) => {
      if (!edge) {
        setSelectedEdge(null);
        setExplanation(null);
        return;
      }

      try {
        const detail = await getGraphEdge(id, edge.id, data?.snapshot_id);
        setSelectedEdge(detail.edge);
        setSelectedNode(null);
        setExplanation(null);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "Failed to load edge details.");
      }
    },
    [id, data],
  );

  const handleExplain = useCallback(async () => {
    if (!selectedEdge && !selectedNode) return;
    setExplaining(true);
    try {
      const res = await explainGraph(
        id,
        selectedEdge
          ? { edge_id: selectedEdge.id, question: "Why does this dependency relationship exist?" }
          : { node_id: selectedNode!.id, question: "What is the architectural purpose of this symbol?" },
        data?.snapshot_id,
      );
      setExplanation(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "AI explanation request failed.");
    } finally {
      setExplaining(false);
    }
  }, [id, selectedEdge, selectedNode, data]);

  const handleToggleRelFilter = useCallback((r: string) => {
    setRelFilter((prev) => (prev.includes(r) ? prev.filter((x) => x !== r) : [...prev, r]));
  }, []);

  const handleToggleNodeFilter = useCallback((t: string) => {
    setNodeFilter((prev) => (prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t]));
  }, []);

  const handleDepthChange = useCallback(
    (d: number) => {
      setDepth(d);
      updateUrlParams(selectedNode?.id ?? null, d);
    },
    [selectedNode, updateUrlParams],
  );

  const handleResetLayout = useCallback(() => {
    setRelFilter([]);
    setNodeFilter([]);
    setSearchQuery("");
    setSelectedNode(null);
    setSelectedEdge(null);
    setFocusedNodeId(null);
    setFitViewTrigger((prev) => prev + 1);
    updateUrlParams(null, 2);
  }, [updateUrlParams]);

  const formatDate = (dateStr?: string | null) => {
    if (!dateStr) return "";
    try {
      const d = new Date(dateStr);
      return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
    } catch {
      return dateStr;
    }
  };

  return (
    <AppShell>
      <div className="mx-auto max-w-[1600px] p-4 sm:p-6 space-y-4 text-foreground">
        {/* Top Navigation Bar Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border pb-3">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Link href="/" className="font-bold text-foreground hover:text-primary transition-colors">
              RepoMind
            </Link>
            <span className="text-muted-foreground/50">Repositories</span>
            <span className="text-muted-foreground/50">&gt;</span>
            <Link href={`/repositories/${id}`} className="text-foreground font-semibold hover:text-primary transition-colors">
              {repo?.name ?? id}
            </Link>
          </div>

          {data && (
            <div className="flex items-center gap-2 text-[11px] text-foreground">
              <span className="flex items-center gap-1 font-semibold text-success">
                <CheckCircle2 className="w-3.5 h-3.5" /> Indexed
              </span>
              <span className="text-muted-foreground">{formatDate(repo?.created_at) || "Recently"}</span>
              <span className="text-muted-foreground/50">·</span>
              <span className="font-mono text-muted-foreground font-bold">
                {data.snapshot_id.slice(0, 7)}
              </span>
            </div>
          )}
        </div>

        {/* Page Title & Overview Metrics */}
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground flex items-center gap-2.5">
              Dependency &amp; Code Graph
            </h1>
            <p className="text-xs text-muted-foreground mt-1">
              Explore how files, modules, classes and functions connect across this repository.
            </p>
          </div>

          {data && (
            <GraphOverview
              nodes={data.nodes}
              edges={data.edges}
              onFocusNode={handleSelectNode}
            />
          )}
        </div>

        {/* Disabled Banner */}
        {disabled && (
          <div className="rounded-xl border border-amber-800/80 bg-amber-950/40 p-4 text-xs text-amber-200 flex items-center gap-3" role="alert">
            <AlertCircle className="w-5 h-5 text-amber-400 flex-shrink-0" />
            <div>
              <p className="font-semibold">Dependency graph is disabled for this deployment.</p>
              <p className="text-amber-300/80 mt-0.5">Code search, overview, and repository chat remain fully active.</p>
              <p className="text-amber-300/80 mt-0.5">To enable locally, set DEPENDENCY_GRAPH=true in backend/.env and restart the backend. Repositories indexed while the graph was disabled must be reindexed before graph data appears.</p>
            </div>
          </div>
        )}

        {/* Error Banner */}
        {error && (
          <div className="rounded-xl border border-rose-800/80 bg-rose-950/40 p-4 text-xs text-rose-200 flex items-center justify-between gap-4" role="alert">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />
              <span>{error}</span>
            </div>
            <Button
              variant="outline"
              size="sm"
              className="h-8 border-rose-700 bg-rose-900/60 text-rose-100 hover:bg-rose-800 text-xs gap-1.5"
              onClick={() => {
                setError(null);
                setLoading(true);
              }}
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Retry
            </Button>
          </div>
        )}

        {/* Loading Skeleton */}
        {loading && (
          <div className="flex flex-col items-center justify-center py-24 border border-border rounded-xl bg-background space-y-3" role="status">
            <div className="p-3 rounded-full bg-primary/20 border border-primary/50 text-primary animate-pulse">
              <GitBranch className="w-8 h-8" />
            </div>
            <p className="text-sm font-bold text-foreground">Building repository graph...</p>
            <p className="text-xs text-muted-foreground">Analyzing AST symbols, imports, and function calls.</p>
          </div>
        )}

        {/* Main Graph Content */}
        {!loading && data && (
          <div className="space-y-4">
            {/* Toolbar */}
            <GraphToolbar
              searchQuery={searchQuery}
              onSearchChange={setSearchQuery}
              relFilter={relFilter}
              onToggleRelFilter={handleToggleRelFilter}
              onClearRelFilters={() => setRelFilter([])}
              nodeFilter={nodeFilter}
              onToggleNodeFilter={handleToggleNodeFilter}
              onClearNodeFilters={() => setNodeFilter([])}
              depth={depth}
              onDepthChange={handleDepthChange}
              onFitView={() => setFitViewTrigger((prev) => prev + 1)}
              onReset={handleResetLayout}
              hasActiveFocus={Boolean(focusedNodeId)}
              onClearFocus={() => {
                setFocusedNodeId(null);
                setSelectedNode(null);
              }}
            />

            {/* Truncation Notice */}
            {data.truncated && (
              <div className="text-xs text-amber-300 bg-amber-950/30 border border-amber-800/60 px-3 py-2 rounded-lg flex items-center gap-2" role="status">
                <AlertCircle className="w-4 h-4 text-amber-400 flex-shrink-0" />
                <span>
                  Results truncated ({data.limit_reason ?? "limit"}; max {data.limits.max_nodes} nodes / {data.limits.max_edges} edges). Refine filters or select a node to expand.
                </span>
              </div>
            )}

            {/* Empty Graph State */}
            {data.nodes.length === 0 && (
              <div className="flex flex-col items-center justify-center p-12 border border-border bg-background rounded-xl text-center space-y-2">
                <p className="text-sm font-semibold text-foreground">No dependency relationships found for this view.</p>
                <p className="text-xs text-muted-foreground max-w-md">
                  Try increasing the graph depth, clearing filters, or ensuring the repository has finished indexing.
                </p>
                <Button variant="outline" size="sm" onClick={handleResetLayout} className="mt-2 text-xs border-border">
                  Reset filters &amp; view
                </Button>
              </div>
            )}

            {/* 3-COLUMN MAIN LAYOUT */}
            {data.nodes.length > 0 && (
              <div className="flex flex-col lg:flex-row gap-4 items-start">
                {/* Left Column: Legend */}
                <GraphLegend
                  showLabels={showLabels}
                  onToggleShowLabels={setShowLabels}
                />

                {/* Center Column: Graph Canvas + Text Alternative */}
                <div className="flex-1 min-w-0 space-y-4 w-full">
                  <GraphCanvas
                    nodes={data.nodes}
                    edges={data.edges}
                    selectedNodeId={selectedNode?.id ?? null}
                    selectedEdgeId={selectedEdge?.id ?? null}
                    onSelectNode={handleSelectNode}
                    onSelectEdge={handleSelectEdge}
                    searchQuery={searchQuery}
                    focusedNodeId={focusedNodeId}
                    onSetFocusedNodeId={setFocusedNodeId}
                    showLabels={showLabels}
                    fitViewTrigger={fitViewTrigger}
                  />

                  {/* Accessible Text Alternative */}
                  <GraphTextAlternative
                    nodes={data.nodes}
                    edges={data.edges}
                    nodeById={nodeById}
                    onSelectNode={handleSelectNode}
                    onSelectEdge={handleSelectEdge}
                  />
                </div>

                {/* Right Column: Inspector */}
                <GraphInspector
                  repositoryId={id}
                  selectedNode={selectedNode}
                  selectedEdge={selectedEdge}
                  nodeById={nodeById}
                  incomingEdges={incomingEdges}
                  outgoingEdges={outgoingEdges}
                  onSelectNode={handleSelectNode}
                  onExplain={handleExplain}
                  explaining={explaining}
                  explanation={explanation}
                  onFocusNode={(node) => setFocusedNodeId(node.id)}
                  onClose={() => {
                    setSelectedNode(null);
                    setSelectedEdge(null);
                    setFocusedNodeId(null);
                  }}
                />
              </div>
            )}
          </div>
        )}
      </div>
    </AppShell>
  );
}
