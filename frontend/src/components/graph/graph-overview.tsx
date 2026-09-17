import React from "react";
import { GitBranch, Link as LinkIcon, Trophy } from "lucide-react";
import type { GraphEdge, GraphNode } from "@/lib/graph-types";
import { getMostConnectedNodes } from "./layout-utils";

interface GraphOverviewProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onFocusNode: (node: GraphNode) => void;
}

export function GraphOverview({ nodes, edges, onFocusNode }: GraphOverviewProps) {
  const topConnected = React.useMemo(
    () => getMostConnectedNodes(nodes, edges, 3),
    [nodes, edges],
  );

  return (
    <div className="flex flex-wrap items-center gap-3 text-xs text-foreground">
      {/* Nodes Card */}
      <div className="flex items-center gap-3 p-3 rounded-xl bg-background border border-border min-w-[130px] shadow-sm">
        <div className="p-2 rounded-lg bg-primary/15 text-primary border border-primary/30">
          <GitBranch className="w-4 h-4" />
        </div>
        <div>
          <span className="text-base font-bold text-foreground font-mono leading-none block">
            {nodes.length}
          </span>
          <span className="text-[10px] text-muted-foreground font-medium">Nodes</span>
        </div>
      </div>

      {/* Relationships Card */}
      <div className="flex items-center gap-3 p-3 rounded-xl bg-background border border-border min-w-[140px] shadow-sm">
        <div className="p-2 rounded-lg bg-primary/15 text-primary border border-primary/30">
          <LinkIcon className="w-4 h-4" />
        </div>
        <div>
          <span className="text-base font-bold text-foreground font-mono leading-none block">
            {edges.length}
          </span>
          <span className="text-[10px] text-muted-foreground font-medium">Relationships</span>
        </div>
      </div>

      {/* Most Connected Card */}
      <div className="flex flex-col justify-center p-3 rounded-xl bg-background border border-border min-w-[210px] shadow-sm flex-1 sm:flex-initial">
        <div className="flex items-center gap-1.5 text-[10px] font-bold text-foreground mb-1.5">
          <Trophy className="w-3.5 h-3.5 text-primary" />
          Most connected
        </div>

        <div className="space-y-0.5 font-mono text-[11px]">
          {topConnected.length === 0 ? (
            <span className="text-muted-foreground text-[10px]">No connected nodes detected</span>
          ) : (
            topConnected.map(({ node, connections }, idx) => (
              <button
                key={node.id}
                onClick={() => onFocusNode(node)}
                className="w-full flex items-center justify-between text-left px-1.5 py-0.5 rounded-md hover:bg-accent transition-colors group"
              >
                <span className="text-foreground truncate max-w-[150px] group-hover:text-primary">
                  {idx + 1}. {node.name}
                </span>
                <span className="text-muted-foreground font-bold text-[10px] ml-2">
                  {connections}
                </span>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
