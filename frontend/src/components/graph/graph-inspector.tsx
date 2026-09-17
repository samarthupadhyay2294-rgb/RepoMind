import React, { useMemo, useState } from "react";
import Link from "next/link";
import {
  ExternalLink,
  Sparkles,
  ArrowRight,
  Info,
  ShieldCheck,
  AlertTriangle,
  Code2,
  Focus,
  X,
} from "lucide-react";
import type {
  GraphEdge,
  GraphExplainResponse,
  GraphNode,
} from "@/lib/graph-types";
import { getNodeTypeConfig } from "./custom-node";
import { getEdgeColor } from "./custom-edge";

interface GraphInspectorProps {
  repositoryId: string;
  selectedNode: GraphNode | null;
  selectedEdge: GraphEdge | null;
  nodeById: Map<string, GraphNode>;
  incomingEdges: GraphEdge[];
  outgoingEdges: GraphEdge[];
  onSelectNode: (node: GraphNode) => void;
  onExplain: () => void;
  explaining: boolean;
  explanation: GraphExplainResponse | null;
  onFocusNode: (node: GraphNode) => void;
  onClose: () => void;
}

export function GraphInspector({
  repositoryId,
  selectedNode,
  selectedEdge,
  nodeById,
  incomingEdges,
  outgoingEdges,
  onSelectNode,
  onExplain,
  explaining,
  explanation,
  onFocusNode,
  onClose,
}: GraphInspectorProps) {
  const [activeTab, setActiveTab] = useState<"overview" | "relationships" | "source">("overview");

  // Calculate node type counts connected to selected node
  const connectedNodeTypeCounts = useMemo(() => {
    const counts: Record<string, number> = {
      Files: 0,
      Directories: 0,
      Modules: 0,
      Classes: 0,
      Functions: 0,
      Methods: 0,
      Interfaces: 0,
      Types: 0,
      Enums: 0,
    };

    const allEdges = [...incomingEdges, ...outgoingEdges];
    allEdges.forEach((edge) => {
      const otherId = edge.source === selectedNode?.id ? edge.target : edge.source;
      const otherNode = nodeById.get(otherId);
      if (!otherNode) return;
      const t = otherNode.type.toLowerCase();
      if (t === "file") counts.Files += 1;
      else if (t === "directory") counts.Directories += 1;
      else if (t === "module") counts.Modules += 1;
      else if (t === "class") counts.Classes += 1;
      else if (t === "function") counts.Functions += 1;
      else if (t === "method") counts.Methods += 1;
      else if (t === "interface") counts.Interfaces += 1;
      else if (t === "type") counts.Types += 1;
      else if (t === "enum") counts.Enums += 1;
    });

    return counts;
  }, [incomingEdges, outgoingEdges, selectedNode, nodeById]);

  // Calculate relationship type counts
  const relTypeCounts = useMemo(() => {
    const counts: Record<string, number> = {
      Imports: 0,
      Calls: 0,
      References: 0,
      Inherits: 0,
      Implements: 0,
      "Uses Type": 0,
    };

    const allEdges = [...incomingEdges, ...outgoingEdges];
    allEdges.forEach((edge) => {
      const r = edge.relationship_type.toLowerCase();
      if (r === "imports") counts.Imports += 1;
      else if (r === "calls") counts.Calls += 1;
      else if (r === "references") counts.References += 1;
      else if (r === "inherits") counts.Inherits += 1;
      else if (r === "implements") counts.Implements += 1;
      else if (r === "uses_type") counts["Uses Type"] += 1;
    });

    return counts;
  }, [incomingEdges, outgoingEdges]);

  if (!selectedNode && !selectedEdge) {
    return (
      <div className="flex flex-col items-center justify-center p-6 text-center bg-background border border-border rounded-xl h-full min-h-[420px] w-full lg:w-80 flex-shrink-0 shadow-md">
        <div className="p-3 rounded-full bg-accent border border-border mb-3 text-primary">
          <Info className="w-6 h-6" />
        </div>
        <h3 className="text-sm font-bold text-foreground">Explore the graph</h3>
        <p className="text-[11px] text-muted-foreground mt-1.5 max-w-[220px] leading-relaxed">
          Select a node or relationship to inspect source location, connections, related symbols, and AI explanations.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-0 p-0 bg-background border border-border rounded-xl text-xs text-foreground w-full lg:w-80 flex-shrink-0 shadow-md max-h-[calc(100vh-340px)] overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">
          {selectedNode ? "Selected Node" : "Selected Edge"}
        </span>
        <button
          onClick={onClose}
          className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
          aria-label="Close inspector"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* NODE INSPECTOR VIEW */}
        {selectedNode && (
          <div className="space-y-4">
            {/* Card Header info */}
            <div className="flex items-start gap-3">
              {(() => {
                const config = getNodeTypeConfig(selectedNode.type);
                const Icon = config.icon;
                return (
                  <div className={`p-2.5 rounded-xl border flex-shrink-0 ${config.color}`}>
                    <Icon className="w-5 h-5" />
                  </div>
                );
              })()}

              <div className="min-w-0 flex-1">
                <h2 className="text-sm font-bold text-foreground truncate" title={selectedNode.name}>
                  {selectedNode.name}
                </h2>
                <span className="text-[11px] text-muted-foreground capitalize block">
                  {selectedNode.type}
                </span>
                <p className="text-[10px] font-mono text-muted-foreground truncate mt-0.5" title={selectedNode.path}>
                  {selectedNode.path || selectedNode.name}
                </p>
                <div className="mt-2">
                  <span className="text-[10px] font-mono px-2 py-1 rounded-md bg-accent border border-border text-foreground">
                    {incomingEdges.length + outgoingEdges.length} connections
                  </span>
                </div>
              </div>
            </div>

            {/* Navigation Tabs */}
            <div className="flex border-b border-border text-[11px] font-semibold">
              {(["overview", "relationships", "source"] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`py-2 px-3 border-b-2 capitalize transition-colors ${
                    activeTab === tab
                      ? "border-primary text-primary"
                      : "border-transparent text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {tab}
                </button>
              ))}
            </div>

            {/* TAB 1: OVERVIEW */}
            {activeTab === "overview" && (
              <div className="space-y-3">
                {/* Description */}
                <div className="p-3 rounded-lg bg-accent border border-border space-y-1">
                  <span className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground">Description</span>
                  <p className="text-[11px] text-foreground leading-relaxed">
                    {selectedNode.signature
                      ? selectedNode.signature
                      : `Repository ${selectedNode.type} component defined at ${selectedNode.path || selectedNode.name}.`}
                  </p>
                </div>

                {/* Connected Nodes Breakdown */}
                <div className="space-y-1.5">
                  <span className="text-[10px] font-bold text-muted-foreground block uppercase tracking-wider">
                    Connected Nodes
                  </span>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] text-foreground bg-accent p-3 rounded-lg border border-border">
                    {Object.entries(connectedNodeTypeCounts)
                      .filter(([, count]) => count > 0)
                      .map(([type, count]) => (
                        <div key={type} className="flex justify-between items-center py-0.5">
                          <span className="text-muted-foreground">{type}</span>
                          <span className="font-mono font-bold text-foreground">{count}</span>
                        </div>
                      ))}
                  </div>
                </div>

                {/* Relationships Breakdown */}
                <div className="space-y-1.5">
                  <span className="text-[10px] font-bold text-muted-foreground block uppercase tracking-wider">
                    Relationships
                  </span>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] text-foreground bg-accent p-3 rounded-lg border border-border">
                    {Object.entries(relTypeCounts)
                      .filter(([, count]) => count > 0)
                      .map(([rel, count]) => (
                        <div key={rel} className="flex justify-between items-center py-0.5">
                          <span className="text-muted-foreground">{rel}</span>
                          <span className="font-mono font-bold text-primary">{count}</span>
                        </div>
                      ))}
                  </div>
                </div>
              </div>
            )}

            {/* TAB 2: RELATIONSHIPS */}
            {activeTab === "relationships" && (
              <div className="space-y-2">
                <span className="text-[10px] font-bold text-muted-foreground block uppercase tracking-wider">
                  Direct Connections ({incomingEdges.length + outgoingEdges.length})
                </span>
                <div className="space-y-1 max-h-60 overflow-y-auto pr-1">
                  {outgoingEdges.map((edge) => {
                    const targetNode = nodeById.get(edge.target);
                    const edgeColor = getEdgeColor(edge.relationship_type);
                    return (
                      <button
                        key={edge.id}
                        onClick={() => targetNode && onSelectNode(targetNode)}
                        className="w-full flex items-center justify-between p-2 rounded-lg bg-accent border border-border hover:border-primary transition-all text-left"
                      >
                        <span className="truncate text-[11px] text-foreground">
                          <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded mr-1.5" style={{ color: edgeColor, backgroundColor: `${edgeColor}15` }}>
                            {edge.relationship_type}
                          </span>
                          {targetNode ? targetNode.name : edge.target}
                        </span>
                        <ArrowRight className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />
                      </button>
                    );
                  })}

                  {incomingEdges.map((edge) => {
                    const srcNode = nodeById.get(edge.source);
                    const edgeColor = getEdgeColor(edge.relationship_type);
                    return (
                      <button
                        key={edge.id}
                        onClick={() => srcNode && onSelectNode(srcNode)}
                        className="w-full flex items-center justify-between p-2 rounded-lg bg-accent border border-border hover:border-primary transition-all text-left"
                      >
                        <span className="truncate text-[11px] text-foreground">
                          <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded mr-1.5" style={{ color: edgeColor, backgroundColor: `${edgeColor}15` }}>
                            {edge.relationship_type}
                          </span>
                          {srcNode ? srcNode.name : edge.source}
                        </span>
                        <ArrowRight className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0 rotate-180" />
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* TAB 3: SOURCE */}
            {activeTab === "source" && (
              <div className="space-y-2 font-mono text-[11px]">
                <div className="p-3 rounded-lg bg-accent border border-border space-y-1">
                  <span className="text-muted-foreground block text-[9px] uppercase font-sans font-bold">File Path</span>
                  <span className="text-foreground break-all">{selectedNode.path || "N/A"}</span>
                </div>
                <div className="p-3 rounded-lg bg-accent border border-border space-y-1">
                  <span className="text-muted-foreground block text-[9px] uppercase font-sans font-bold">Line Range</span>
                  <span className="text-foreground">
                    Lines {selectedNode.start_line} to {selectedNode.end_line}
                  </span>
                </div>
                <div className="p-3 rounded-lg bg-accent border border-border space-y-1">
                  <span className="text-muted-foreground block text-[9px] uppercase font-sans font-bold">Provenance</span>
                  <span className="text-foreground capitalize">{selectedNode.provenance}</span>
                </div>
              </div>
            )}

            {/* ACTION BUTTONS */}
            <div className="space-y-2 pt-3 border-t border-border">
              {selectedNode.path && (
                <Link
                  href={`/repositories/${repositoryId}?path=${encodeURIComponent(selectedNode.path)}`}
                  className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-lg bg-primary hover:bg-primary/80 text-foreground font-semibold text-xs transition-colors shadow-md shadow-purple-950/40"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  Open in source
                </Link>
              )}

              <button
                onClick={onExplain}
                disabled={explaining}
                className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-lg bg-accent border border-border text-foreground hover:bg-border font-medium text-xs transition-colors disabled:opacity-50"
              >
                <Sparkles className="w-3.5 h-3.5 text-primary" />
                {explaining ? "Explaining..." : "Explain this node"}
              </button>

              <button
                onClick={() => onFocusNode(selectedNode)}
                className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-lg bg-accent border border-border text-foreground hover:bg-border font-medium text-xs transition-colors"
              >
                <Focus className="w-3.5 h-3.5 text-primary" />
                Focus on this node
              </button>
            </div>
          </div>
        )}

        {/* EDGE INSPECTOR VIEW */}
        {selectedEdge && (
          <div className="space-y-4">
            <div className="border-b border-border pb-2">
              <span className="text-[9px] font-bold uppercase text-primary tracking-wider">
                Relationship Edge
              </span>
              <h2 className="text-sm font-bold text-foreground flex items-center gap-1.5 mt-1">
                <span
                  className="font-mono px-2 py-0.5 rounded-md text-[11px] font-bold"
                  style={{
                    color: getEdgeColor(selectedEdge.relationship_type),
                    backgroundColor: `${getEdgeColor(selectedEdge.relationship_type)}15`,
                  }}
                >
                  {selectedEdge.relationship_type}
                </span>
              </h2>
            </div>

            <div className="flex flex-col gap-2 p-3 bg-accent border border-border rounded-lg text-[11px]">
              <div className="truncate font-semibold text-foreground">
                Source: {nodeById.get(selectedEdge.source)?.name ?? selectedEdge.source}
              </div>
              <div
                className="font-mono text-[11px] font-bold flex items-center gap-1"
                style={{ color: getEdgeColor(selectedEdge.relationship_type) }}
              >
                ↓ {selectedEdge.relationship_type}
              </div>
              <div className="truncate font-semibold text-foreground">
                Target: {nodeById.get(selectedEdge.target)?.name ?? selectedEdge.target}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <div className="bg-accent border border-border p-2 rounded-lg flex items-center gap-1.5">
                <ShieldCheck className="w-4 h-4 text-success" />
                <div>
                  <span className="text-muted-foreground block text-[9px] uppercase font-bold">Confidence</span>
                  <span className="font-mono font-bold text-foreground">
                    {(selectedEdge.confidence * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
              <div className="bg-accent border border-border p-2 rounded-lg flex items-center gap-1.5">
                <Code2 className="w-4 h-4 text-primary" />
                <div>
                  <span className="text-muted-foreground block text-[9px] uppercase font-bold">Provenance</span>
                  <span className="capitalize text-foreground">{selectedEdge.provenance}</span>
                </div>
              </div>
            </div>

            {selectedEdge.provenance === "inferred" && (
              <div className="flex items-center gap-2 p-2.5 rounded-lg bg-warning/10 border border-warning/30 text-warning text-[11px]">
                <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                <span>Inferred dependency — derived from AST context analysis.</span>
              </div>
            )}

            <button
              onClick={onExplain}
              disabled={explaining}
              className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-lg bg-primary hover:bg-primary/80 text-foreground font-medium text-xs transition-colors disabled:opacity-50"
            >
              <Sparkles className="w-3.5 h-3.5" />
              {explaining ? "Explaining..." : "Explain relationship with AI"}
            </button>
          </div>
        )}

        {/* AI EXPLANATION OUTPUT */}
        {explanation && (
          <div className="border-t border-border pt-4 space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="font-bold text-[11px] text-primary flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5" />
                AI Explanation
              </h3>
              <span className="text-[9px] font-mono px-1.5 py-0.5 rounded-md bg-accent text-primary border border-border font-bold">
                {explanation.confidence} confidence
              </span>
            </div>

            <p className="text-[11px] leading-relaxed text-foreground bg-accent border border-border p-3 rounded-lg">
              {explanation.explanation}
            </p>

            {explanation.evidence && explanation.evidence.length > 0 && (
              <div className="space-y-1">
                <span className="text-[9px] font-bold text-muted-foreground uppercase block tracking-wider">
                  Citations
                </span>
                <ul className="space-y-1 font-mono text-[10px]">
                  {explanation.evidence.map((ev, i) => (
                    <li key={i} className="text-primary bg-accent p-1.5 rounded-md border border-border truncate">
                      {ev.path}:{ev.start_line}-{ev.end_line}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
