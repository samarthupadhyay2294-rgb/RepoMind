import dagre from "@dagrejs/dagre";
import { Position, type Edge, type Node } from "@xyflow/react";
import type { GraphEdge, GraphNode } from "@/lib/graph-types";

export const NODE_WIDTH = 240;
export const NODE_HEIGHT = 90;

export interface LayoutOptions {
  direction?: "TB" | "LR";
  nodeWidth?: number;
  nodeHeight?: number;
}

export function getLayoutedElements(
  nodes: Node[],
  edges: Edge[],
  options: LayoutOptions = {},
): { nodes: Node[]; edges: Edge[] } {
  const {
    direction = "TB",
    nodeWidth = NODE_WIDTH,
    nodeHeight = NODE_HEIGHT,
  } = options;

  if (nodes.length === 0) return { nodes: [], edges: [] };

  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  dagreGraph.setGraph({
    rankdir: direction,
    nodesep: 80,
    ranksep: 120,
    marginx: 20,
    marginy: 20,
  });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  const layoutedNodes: Node[] = nodes.map((node) => {
    const dagreNode = dagreGraph.node(node.id);
    return {
      ...node,
      position: {
        x: dagreNode.x - nodeWidth / 2,
        y: dagreNode.y - nodeHeight / 2,
      },
      targetPosition: Position.Top,
      sourcePosition: Position.Bottom,
    };
  });

  return { nodes: layoutedNodes, edges };
}

/**
 * Calculates connection counts for each node from the edge list.
 */
export function calculateConnectionCounts(
  nodes: GraphNode[],
  edges: GraphEdge[],
): Map<string, { total: number; incoming: number; outgoing: number }> {
  const counts = new Map<string, { total: number; incoming: number; outgoing: number }>();

  nodes.forEach((n) => {
    counts.set(n.id, { total: 0, incoming: 0, outgoing: 0 });
  });

  edges.forEach((e) => {
    const src = counts.get(e.source);
    if (src) {
      src.outgoing += 1;
      src.total += 1;
    }

    const tgt = counts.get(e.target);
    if (tgt) {
      tgt.incoming += 1;
      tgt.total += 1;
    }
  });

  return counts;
}

/**
 * Computes top connected nodes (most connected).
 */
export function getMostConnectedNodes(
  nodes: GraphNode[],
  edges: GraphEdge[],
  limit = 5,
): { node: GraphNode; connections: number }[] {
  const counts = calculateConnectionCounts(nodes, edges);

  const sorted = [...nodes].map((node) => ({
    node,
    connections: counts.get(node.id)?.total ?? 0,
  }));

  sorted.sort((a, b) => b.connections - a.connections);

  return sorted.slice(0, limit);
}

/**
 * Compute bounding box of all nodes.
 */
export function getNodesBounds(nodes: Node[]): { x: number; y: number; width: number; height: number } {
  if (nodes.length === 0) return { x: 0, y: 0, width: 0, height: 0 };

  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;

  nodes.forEach((node) => {
    const x = node.position.x;
    const y = node.position.y;
    if (x < minX) minX = x;
    if (y < minY) minY = y;
    if (x + NODE_WIDTH > maxX) maxX = x + NODE_WIDTH;
    if (y + NODE_HEIGHT > maxY) maxY = y + NODE_HEIGHT;
  });

  return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
}
