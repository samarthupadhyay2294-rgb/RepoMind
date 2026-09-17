import React, { useState } from "react";
import { ListTree, ChevronDown, ChevronUp, FileCode, ArrowRight, Search } from "lucide-react";
import type { GraphEdge, GraphNode } from "@/lib/graph-types";

interface GraphTextAlternativeProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  nodeById: Map<string, GraphNode>;
  onSelectNode: (node: GraphNode) => void;
  onSelectEdge: (edge: GraphEdge) => void;
}

export function GraphTextAlternative({
  nodes,
  edges,
  nodeById,
  onSelectNode,
  onSelectEdge,
}: GraphTextAlternativeProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [filterText, setFilterText] = useState("");

  const filteredNodes = React.useMemo(() => {
    if (!filterText.trim()) return nodes;
    const q = filterText.toLowerCase();
    return nodes.filter(
      (n) =>
        n.name.toLowerCase().includes(q) ||
        n.path.toLowerCase().includes(q) ||
        n.type.toLowerCase().includes(q),
    );
  }, [nodes, filterText]);

  const filteredEdges = React.useMemo(() => {
    if (!filterText.trim()) return edges;
    const q = filterText.toLowerCase();
    return edges.filter((e) => {
      const srcName = nodeById.get(e.source)?.name ?? e.source;
      const tgtName = nodeById.get(e.target)?.name ?? e.target;
      return (
        srcName.toLowerCase().includes(q) ||
        tgtName.toLowerCase().includes(q) ||
        e.relationship_type.toLowerCase().includes(q)
      );
    });
  }, [edges, nodeById, filterText]);

  return (
    <div className="border border-border bg-background rounded-xl text-xs overflow-hidden shadow-sm">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between p-3 text-foreground hover:text-foreground transition-colors"
        aria-expanded={isOpen}
        aria-controls="text-alternative-content"
      >
        <div className="flex items-center gap-2 font-medium">
          <ListTree className="w-3.5 h-3.5 text-primary" />
          <span>Text Alternative</span>
          <span className="text-[10px] text-muted-foreground font-mono">
            ({nodes.length} nodes · {edges.length} edges)
          </span>
        </div>
        <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
          <span>{isOpen ? "Collapse" : "Expand"}</span>
          {isOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </div>
      </button>

      {isOpen && (
        <div id="text-alternative-content" className="p-3 pt-0 border-t border-border space-y-4">
          {/* Quick text filter */}
          <div className="relative pt-3">
            <Search className="absolute left-3 top-5.5 h-3.5 w-3.5 text-muted-foreground" />
            <input
              type="text"
              value={filterText}
              onChange={(e) => setFilterText(e.target.value)}
              placeholder="Filter text view..."
              className="w-full rounded-lg border border-border bg-background pl-9 pr-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none transition-all font-mono"
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Nodes Tree */}
            <div className="space-y-2">
              <h3 className="font-bold text-[11px] uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                <FileCode className="w-3.5 h-3.5 text-primary" />
                Nodes ({filteredNodes.length})
              </h3>
              <ul className="space-y-1 max-h-72 overflow-y-auto pr-1 border border-border rounded-lg p-2 bg-background font-mono text-[11px]">
                {filteredNodes.map((n) => (
                  <li key={n.id} className="flex items-center justify-between gap-2 p-1 hover:bg-accent rounded-md">
                    <button
                      onClick={() => onSelectNode(n)}
                      className="text-primary hover:underline font-semibold truncate text-left"
                    >
                      {n.name}
                    </button>
                    <span className="text-muted-foreground text-[10px] flex-shrink-0">
                      [{n.type}] {n.path}:{n.start_line}
                    </span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Relationships Tree */}
            <div className="space-y-2">
              <h3 className="font-bold text-[11px] uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                <ArrowRight className="w-3.5 h-3.5 text-primary" />
                Relationships ({filteredEdges.length})
              </h3>
              <ul className="space-y-1 max-h-72 overflow-y-auto pr-1 border border-border rounded-lg p-2 bg-background font-mono text-[11px]">
                {filteredEdges.map((e) => {
                  const srcNode = nodeById.get(e.source);
                  const tgtNode = nodeById.get(e.target);
                  return (
                    <li key={e.id} className="p-1 hover:bg-accent rounded-md">
                      <button
                        onClick={() => onSelectEdge(e)}
                        className="text-left w-full hover:underline flex items-center gap-1.5 flex-wrap"
                      >
                        <span className="text-foreground font-semibold">
                          {srcNode ? srcNode.name : e.source}
                        </span>
                        <span className="text-primary font-bold px-1.5 py-0.5 rounded-md bg-primary/10 text-[10px]">
                          {e.relationship_type}
                        </span>
                        <span className="text-foreground font-semibold">
                          {tgtNode ? tgtNode.name : e.target}
                        </span>
                        <span className="text-muted-foreground text-[10px] ml-auto">
                          ({e.provenance}, {(e.confidence * 100).toFixed(0)}%)
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
