import React, { useCallback, useEffect, useMemo, useRef } from "react";
import {
  ReactFlow,
  Background,
  MiniMap,
  useNodesState,
  useEdgesState,
  useReactFlow,
  ReactFlowProvider,
  type Node,
  type Edge,
  type NodeMouseHandler,
  type EdgeMouseHandler,
  BackgroundVariant,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Plus, Minus, Maximize2, RotateCcw, Crosshair } from "lucide-react";

import type { GraphEdge, GraphNode } from "@/lib/graph-types";
import { CustomNodeCard } from "./custom-node";
import { CustomEdge } from "./custom-edge";
import {
  getLayoutedElements,
  calculateConnectionCounts,
} from "./layout-utils";

const nodeTypes = {
  customCard: CustomNodeCard,
};

const edgeTypes = {
  customEdge: CustomEdge,
};

interface GraphCanvasInnerProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  onSelectNode: (node: GraphNode | null) => void;
  onSelectEdge: (edge: GraphEdge | null) => void;
  searchQuery: string;
  focusedNodeId: string | null;
  onSetFocusedNodeId: (id: string | null) => void;
  showLabels: boolean;
  fitViewTrigger: number;
}

function GraphCanvasInner({
  nodes: rawNodes,
  edges: rawEdges,
  selectedNodeId,
  selectedEdgeId,
  onSelectNode,
  onSelectEdge,
  searchQuery,
  focusedNodeId,
  onSetFocusedNodeId,
  showLabels,
  fitViewTrigger,
}: GraphCanvasInnerProps) {
  const { fitView, zoomIn, zoomOut, setCenter } = useReactFlow();
  const containerRef = useRef<HTMLDivElement>(null);

  const [rfNodes, setRfNodes, onNodesChange] = useNodesState<Node>([]);
  const [rfEdges, setRfEdges, onEdgesChange] = useEdgesState<Edge>([]);

  // 1. Connection counts per node
  const connectionCounts = useMemo(
    () => calculateConnectionCounts(rawNodes, rawEdges),
    [rawNodes, rawEdges],
  );

  // 2. Compute Focus Neighborhood
  const focusNeighborhood = useMemo(() => {
    if (!focusedNodeId) return null;
    const neighbors = new Set<string>();
    neighbors.add(focusedNodeId);

    rawEdges.forEach((e) => {
      if (e.source === focusedNodeId) neighbors.add(e.target);
      if (e.target === focusedNodeId) neighbors.add(e.source);
    });

    return neighbors;
  }, [focusedNodeId, rawEdges]);

  // 3. Search matched node IDs
  const searchMatches = useMemo(() => {
    if (!searchQuery.trim()) return new Set<string>();
    const q = searchQuery.toLowerCase();
    const set = new Set<string>();
    rawNodes.forEach((n) => {
      if (
        n.name.toLowerCase().includes(q) ||
        n.path.toLowerCase().includes(q) ||
        n.type.toLowerCase().includes(q)
      ) {
        set.add(n.id);
      }
    });
    return set;
  }, [rawNodes, searchQuery]);

  const rawNodeMap = useMemo(() => {
    const map = new Map<string, GraphNode>();
    rawNodes.forEach((n) => map.set(n.id, n));
    return map;
  }, [rawNodes]);

  const rawEdgeMap = useMemo(() => {
    const map = new Map<string, GraphEdge>();
    rawEdges.forEach((e) => map.set(e.id, e));
    return map;
  }, [rawEdges]);

  // 4. Update React Flow elements and apply Dagre layout
  useEffect(() => {
    if (rawNodes.length === 0) {
      setRfNodes([]);
      setRfEdges([]);
      return;
    }

    const initialNodes: Node[] = rawNodes.map((n) => ({
      id: n.id,
      type: "customCard",
      position: { x: 0, y: 0 },
      data: {
        node: n,
        connectionCount: connectionCounts.get(n.id)?.total ?? 0,
        isSelected: selectedNodeId === n.id,
        isFocused: focusedNodeId === n.id,
        isNeighbor: focusNeighborhood?.has(n.id) ?? false,
        hasActiveFocus: Boolean(focusedNodeId),
        searchMatch: searchMatches.has(n.id),
      },
    }));

    const initialEdges: Edge[] = rawEdges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      type: "customEdge",
      animated: false,
      data: {
        edge: e,
        isSelected: selectedEdgeId === e.id,
        isFocused:
          focusedNodeId !== null &&
          (e.source === focusedNodeId || e.target === focusedNodeId),
        hasActiveFocus: Boolean(focusedNodeId),
        showAlwaysLabel: showLabels,
      },
    }));

    const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(
      initialNodes,
      initialEdges,
      { direction: "TB" },
    );

    setRfNodes(layoutedNodes);
    setRfEdges(layoutedEdges);

    // Fit view after layout settles - use appropriate padding based on node count
    const timer = setTimeout(() => {
      const padding = rawNodes.length <= 5 ? 0.3 : rawNodes.length <= 20 ? 0.2 : 0.12;
      fitView({ padding, duration: 500 });
    }, 80);

    return () => clearTimeout(timer);
  }, [
    rawNodes,
    rawEdges,
    selectedNodeId,
    selectedEdgeId,
    focusedNodeId,
    focusNeighborhood,
    searchMatches,
    connectionCounts,
    showLabels,
    setRfNodes,
    setRfEdges,
    fitView,
  ]);

  useEffect(() => {
    if (fitViewTrigger > 0) {
      const padding = rawNodes.length <= 5 ? 0.3 : rawNodes.length <= 20 ? 0.2 : 0.12;
      fitView({ padding, duration: 400 });
    }
  }, [fitViewTrigger, fitView, rawNodes.length]);

  const handleNodeClick: NodeMouseHandler = useCallback(
    (_, node) => {
      const graphNode = rawNodeMap.get(node.id);
      if (graphNode) {
        onSelectNode(graphNode);
        onSelectEdge(null);
        onSetFocusedNodeId(graphNode.id);
      }
    },
    [rawNodeMap, onSelectNode, onSelectEdge, onSetFocusedNodeId],
  );

  const handleEdgeClick: EdgeMouseHandler = useCallback(
    (_, edge) => {
      const graphEdge = rawEdgeMap.get(edge.id);
      if (graphEdge) {
        onSelectEdge(graphEdge);
        onSelectNode(null);
      }
    },
    [rawEdgeMap, onSelectEdge, onSelectNode],
  );

  const handlePaneClick = useCallback(() => {
    onSelectNode(null);
    onSelectEdge(null);
    onSetFocusedNodeId(null);
  }, [onSelectNode, onSelectEdge, onSetFocusedNodeId]);

  const handleCenterSelected = useCallback(() => {
    if (selectedNodeId) {
      const node = rfNodes.find((n) => n.id === selectedNodeId);
      if (node && node.position) {
        setCenter(node.position.x + 120, node.position.y + 45, { zoom: 1.0, duration: 500 });
        return;
      }
    }
    const padding = rawNodes.length <= 5 ? 0.3 : rawNodes.length <= 20 ? 0.2 : 0.12;
    fitView({ padding, duration: 400 });
  }, [selectedNodeId, rfNodes, setCenter, fitView, rawNodes.length]);

  const handleReset = useCallback(() => {
    onSelectNode(null);
    onSelectEdge(null);
    onSetFocusedNodeId(null);
    const padding = rawNodes.length <= 5 ? 0.3 : rawNodes.length <= 20 ? 0.2 : 0.12;
    fitView({ padding, duration: 400 });
  }, [onSelectNode, onSelectEdge, onSetFocusedNodeId, fitView, rawNodes.length]);

  return (
    <div
      ref={containerRef}
      className="relative w-full rounded-xl border border-border bg-background overflow-hidden shadow-inner"
      style={{ minHeight: "520px", height: "calc(100vh - 340px)", maxHeight: "800px" }}
    >
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        onEdgeClick={handleEdgeClick}
        onPaneClick={handlePaneClick}
        minZoom={0.15}
        maxZoom={2.5}
        defaultViewport={{ x: 0, y: 0, zoom: 0.85 }}
        panOnDrag
        panOnScroll
        zoomOnScroll
        zoomOnPinch
        proOptions={{ hideAttribution: true }}
        defaultEdgeOptions={{
          type: "customEdge",
        }}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="var(--border)" />

        {/* MiniMap - bottom right */}
        <MiniMap
          nodeColor={(node) => {
            const data = node.data as { isSelected?: boolean; node?: { type?: string } };
            if (data?.isSelected) return "var(--primary)";
            const t = data?.node?.type?.toLowerCase();
            if (t === "directory") return "var(--primary)";
            if (t === "file") return "var(--primary)";
            if (t === "class") return "var(--success)";
            if (t === "function") return "var(--primary)";
            return "var(--primary)";
          }}
          maskColor="rgba(11, 13, 21, 0.8)"
          className="!bg-background !border-border !rounded-xl overflow-hidden shadow-lg"
          zoomable
          pannable
          style={{ width: 160, height: 110 }}
        />
      </ReactFlow>

      {/* Floating Viewport Controls - bottom left */}
      <div className="absolute bottom-4 left-4 z-10 flex flex-col items-center gap-1 p-1.5 bg-background/95 backdrop-blur-sm border border-border rounded-xl shadow-lg">
        <button
          onClick={() => zoomIn({ duration: 200 })}
          className="p-2 rounded-lg text-foreground hover:text-foreground hover:bg-accent transition-colors"
          title="Zoom in"
          aria-label="Zoom in"
        >
          <Plus className="w-4 h-4" />
        </button>
        <button
          onClick={() => zoomOut({ duration: 200 })}
          className="p-2 rounded-lg text-foreground hover:text-foreground hover:bg-accent transition-colors"
          title="Zoom out"
          aria-label="Zoom out"
        >
          <Minus className="w-4 h-4" />
        </button>
        <div className="w-full h-px bg-border" />
        <button
          onClick={() => {
            const padding = rawNodes.length <= 5 ? 0.3 : rawNodes.length <= 20 ? 0.2 : 0.12;
            fitView({ padding, duration: 400 });
          }}
          className="p-2 rounded-lg text-foreground hover:text-foreground hover:bg-accent transition-colors"
          title="Fit graph to viewport"
          aria-label="Fit graph"
        >
          <Maximize2 className="w-4 h-4" />
        </button>
        <button
          onClick={handleCenterSelected}
          className="p-2 rounded-lg text-foreground hover:text-foreground hover:bg-accent transition-colors"
          title="Center selection"
          aria-label="Center selection"
        >
          <Crosshair className="w-4 h-4" />
        </button>
        <div className="w-full h-px bg-border" />
        <button
          onClick={handleReset}
          className="p-2 rounded-lg text-foreground hover:text-foreground hover:bg-accent transition-colors"
          title="Reset view"
          aria-label="Reset view"
        >
          <RotateCcw className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}

export function GraphCanvas(props: GraphCanvasInnerProps) {
  return (
    <ReactFlowProvider>
      <GraphCanvasInner {...props} />
    </ReactFlowProvider>
  );
}
