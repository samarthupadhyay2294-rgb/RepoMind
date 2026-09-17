import React, { memo, useState } from "react";
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type EdgeProps,
} from "@xyflow/react";
import type { GraphEdge } from "@/lib/graph-types";

export interface CustomEdgeData extends Record<string, unknown> {
  edge: GraphEdge;
  isSelected: boolean;
  isFocused: boolean;
  hasActiveFocus: boolean;
  showAlwaysLabel: boolean;
}

export const REL_COLORS: Record<string, string> = {
  imports: "var(--primary)",
  calls: "var(--success)",
  references: "var(--primary)",
  inherits: "var(--warning)",
  implements: "var(--destructive)",
  uses_type: "var(--primary)",
  contains: "var(--warning)",
  exports: "var(--primary)",
};

export function getEdgeColor(relType: string): string {
  const norm = relType.toLowerCase();
  return REL_COLORS[norm] ?? "var(--primary)";
}

export const CustomEdge = memo(({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
}: EdgeProps) => {
  const [isHovered, setIsHovered] = useState(false);
  const edgeData = data as unknown as CustomEdgeData | undefined;
  const graphEdge = edgeData?.edge;

  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
    curvature: 0.3,
  });

  const isSelected = edgeData?.isSelected ?? false;
  const isFocused = edgeData?.isFocused ?? false;
  const hasActiveFocus = edgeData?.hasActiveFocus ?? false;
  const showAlwaysLabel = edgeData?.showAlwaysLabel ?? false;
  const isInferred = graphEdge?.provenance === "inferred";

  const relType = graphEdge?.relationship_type ?? "connects";
  const baseColor = getEdgeColor(relType);

  let strokeColor = baseColor;
  let strokeWidth = 1.5;
  let opacity = 0.7;

  if (isSelected) {
    strokeColor = baseColor;
    strokeWidth = 2.5;
    opacity = 1;
  } else if (isFocused) {
    strokeColor = baseColor;
    strokeWidth = 2;
    opacity = 1;
  } else if (isHovered) {
    strokeColor = baseColor;
    strokeWidth = 2;
    opacity = 1;
  } else if (hasActiveFocus && !isFocused) {
    opacity = 0.1;
  }

  const showLabel = showAlwaysLabel || isHovered || isSelected || isFocused;

  const markerId = `arrow-${id}`;

  return (
    <>
      <defs>
        <marker
          id={markerId}
          viewBox="0 0 10 7"
          refX="10"
          refY="3.5"
          markerWidth="8"
          markerHeight="6"
          orient="auto-start-reverse"
        >
          <path d="M 0 0 L 10 3.5 L 0 7 z" fill={strokeColor} fillOpacity={opacity} />
        </marker>
      </defs>
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: strokeColor,
          strokeWidth,
          strokeDasharray: isInferred ? "6 4" : undefined,
          opacity,
          transition: "stroke 0.15s ease, stroke-width 0.15s ease, opacity 0.15s ease",
        }}
      />
      {/* Arrow marker */}
      <path
        d={edgePath}
        fill="none"
        stroke="none"
        markerEnd={`url(#${markerId})`}
      />
      {/* Invisible wider path for hovering */}
      <path
        d={edgePath}
        fill="none"
        stroke="transparent"
        strokeWidth={16}
        className="cursor-pointer"
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      />

      {showLabel && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: "absolute",
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              pointerEvents: "all",
            }}
            className="nodrag nopan"
          >
            <span
              className={`px-2 py-0.5 rounded-md text-[9px] font-mono font-bold border shadow-sm transition-all ${
                isSelected
                  ? "bg-purple-950/80 text-purple-200 border-purple-500/60"
                  : "bg-background/90 text-foreground border-border/80"
              }`}
              style={{ color: isSelected ? undefined : baseColor }}
            >
              {relType}
            </span>
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
});

CustomEdge.displayName = "CustomEdge";
