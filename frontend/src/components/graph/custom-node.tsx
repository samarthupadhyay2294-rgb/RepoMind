import React, { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import {
  Folder,
  FileCode,
  Box,
  User,
  Code,
  Braces,
  Shield,
  FileType,
  Tag,
  Link2,
} from "lucide-react";
import type { GraphNode } from "@/lib/graph-types";

export interface CustomNodeData extends Record<string, unknown> {
  node: GraphNode;
  connectionCount: number;
  isSelected: boolean;
  isFocused: boolean;
  isNeighbor: boolean;
  hasActiveFocus: boolean;
  searchMatch: boolean;
}

export const getNodeTypeConfig = (type: string) => {
  const normalized = type.toLowerCase();
  switch (normalized) {
    case "directory":
      return {
        icon: Folder,
        label: "Directory",
        color: "text-purple-400 bg-purple-500/10 border-purple-500/30",
        accentColor: "var(--primary)",
        badgeBg: "bg-purple-500/15 text-purple-300",
      };
    case "file":
      return {
        icon: FileCode,
        label: "File",
        color: "text-blue-400 bg-blue-500/10 border-blue-500/30",
        accentColor: "var(--primary)",
        badgeBg: "bg-blue-500/15 text-blue-300",
      };
    case "module":
      return {
        icon: Box,
        label: "Module",
        color: "text-violet-400 bg-violet-500/10 border-violet-500/30",
        accentColor: "var(--primary)",
        badgeBg: "bg-violet-500/15 text-violet-300",
      };
    case "class":
      return {
        icon: User,
        label: "Class",
        color: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30",
        accentColor: "var(--success)",
        badgeBg: "bg-emerald-500/15 text-emerald-300",
      };
    case "function":
      return {
        icon: Code,
        label: "Function",
        color: "text-sky-400 bg-sky-500/10 border-sky-500/30",
        accentColor: "var(--primary)",
        badgeBg: "bg-sky-500/15 text-sky-300",
      };
    case "method":
      return {
        icon: Braces,
        label: "Method",
        color: "text-purple-400 bg-purple-500/10 border-purple-500/30",
        accentColor: "var(--primary)",
        badgeBg: "bg-purple-500/15 text-purple-300",
      };
    case "interface":
      return {
        icon: Shield,
        label: "Interface",
        color: "text-red-400 bg-red-500/10 border-red-500/30",
        accentColor: "var(--destructive)",
        badgeBg: "bg-red-500/15 text-red-300",
      };
    case "type":
      return {
        icon: FileType,
        label: "Type",
        color: "text-cyan-400 bg-cyan-500/10 border-cyan-500/30",
        accentColor: "var(--primary)",
        badgeBg: "bg-cyan-500/15 text-cyan-300",
      };
    case "enum":
      return {
        icon: Tag,
        label: "Enum",
        color: "text-rose-400 bg-rose-500/10 border-rose-500/30",
        accentColor: "var(--destructive)",
        badgeBg: "bg-rose-500/15 text-rose-300",
      };
    default:
      return {
        icon: FileCode,
        label: type,
        color: "text-slate-400 bg-slate-500/10 border-slate-500/30",
        accentColor: "var(--muted-foreground)",
        badgeBg: "bg-slate-500/15 text-slate-300",
      };
  }
};

export const CustomNodeCard = memo(({ data }: NodeProps) => {
  const nodeData = data as unknown as CustomNodeData;
  const { node, connectionCount, isSelected, isFocused, isNeighbor, hasActiveFocus, searchMatch } =
    nodeData;

  const config = getNodeTypeConfig(node.type);
  const Icon = config.icon;

  let opacityClass = "opacity-100";
  if (hasActiveFocus) {
    if (isFocused) opacityClass = "opacity-100 z-30";
    else if (isNeighbor) opacityClass = "opacity-100 z-20";
    else opacityClass = "opacity-30";
  }

  let borderStyle = "border-border bg-background";
  let shadowStyle = "";
  if (isSelected) {
    borderStyle = "border-primary bg-accent";
    shadowStyle = "shadow-lg shadow-purple-500/10";
  } else if (isFocused) {
    borderStyle = "border-primary bg-accent";
    shadowStyle = "shadow-md shadow-purple-500/5";
  } else if (isNeighbor) {
    borderStyle = "border-primary/50 bg-background";
  } else if (searchMatch) {
    borderStyle = "border-warning bg-background";
    shadowStyle = "shadow-md shadow-amber-500/10";
  }

  const filename = node.path ? node.path.split("/").pop() ?? node.name : node.name;
  const lineCount = node.end_line && node.start_line ? node.end_line - node.start_line + 1 : null;

  return (
    <div
      className={`group relative w-[220px] rounded-xl border transition-all duration-200 cursor-pointer ${borderStyle} ${shadowStyle} ${opacityClass}`}
      role="button"
      tabIndex={0}
      aria-label={`${node.name} (${node.type})`}
    >
      {/* Top accent line */}
      <div
        className="absolute top-0 left-3 right-3 h-[2px] rounded-b-full opacity-60"
        style={{ backgroundColor: config.accentColor }}
      />

      <Handle
        type="target"
        position={Position.Top}
        className="!w-2.5 !h-2.5 !bg-border !border-2 !border-background group-hover:!bg-primary transition-colors"
      />

      <div className="p-3 pt-3.5">
        <div className="flex items-start gap-2.5">
          <div className={`p-2 rounded-lg border flex-shrink-0 ${config.color}`}>
            <Icon className="w-4 h-4" />
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <span
                className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-md ${config.badgeBg}`}
              >
                {config.label}
              </span>
              {connectionCount > 0 && (
                <span className="flex items-center gap-0.5 text-[9px] text-muted-foreground bg-accent px-1.5 py-0.5 rounded-md border border-border font-mono">
                  <Link2 className="w-2.5 h-2.5" />
                  {connectionCount}
                </span>
              )}
            </div>

            <h3
              className="text-[11px] font-bold text-foreground truncate mt-1.5 tracking-tight leading-tight"
              title={node.name}
            >
              {node.name}
            </h3>

            <p className="text-[10px] text-muted-foreground truncate font-mono mt-0.5 leading-tight" title={node.path || filename}>
              {lineCount ? `${lineCount} lines` : filename}
            </p>
          </div>
        </div>
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-2.5 !h-2.5 !bg-border !border-2 !border-background group-hover:!bg-primary transition-colors"
      />
    </div>
  );
});

CustomNodeCard.displayName = "CustomNodeCard";
