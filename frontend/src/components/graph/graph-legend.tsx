import React, { useState } from "react";
import {
  FileCode,
  Folder,
  Box,
  User,
  Code,
  Braces,
  Shield,
  FileType,
  Tag,
  ArrowRight,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

interface GraphLegendProps {
  showLabels: boolean;
  onToggleShowLabels: (show: boolean) => void;
}

export const NODE_LEGEND_ITEMS = [
  { label: "File", icon: FileCode, color: "text-primary bg-primary/10" },
  { label: "Directory", icon: Folder, color: "text-primary bg-primary/10" },
  { label: "Module", icon: Box, color: "text-primary bg-primary/10" },
  { label: "Class", icon: User, color: "text-success bg-success/10" },
  { label: "Function", icon: Code, color: "text-primary bg-primary/10" },
  { label: "Method", icon: Braces, color: "text-primary bg-primary/10" },
  { label: "Interface", icon: Shield, color: "text-destructive bg-destructive/10" },
  { label: "Type", icon: FileType, color: "text-primary bg-primary/10" },
  { label: "Enum", icon: Tag, color: "text-destructive bg-destructive/10" },
];

export const REL_LEGEND_ITEMS = [
  { label: "Imports", color: "var(--primary)", text: "text-primary" },
  { label: "Calls", color: "var(--success)", text: "text-success" },
  { label: "References", color: "var(--primary)", text: "text-primary" },
  { label: "Inherits", color: "var(--warning)", text: "text-warning" },
  { label: "Implements", color: "var(--destructive)", text: "text-destructive" },
  { label: "Uses Type", color: "var(--primary)", text: "text-primary" },
];

export function GraphLegend({ showLabels, onToggleShowLabels }: GraphLegendProps) {
  const [collapsed, setCollapsed] = useState(false);

  if (collapsed) {
    return (
      <div className="flex flex-col items-center py-3 px-1.5 bg-background border border-border rounded-xl text-xs text-foreground flex-shrink-0 shadow-md">
        <button
          onClick={() => setCollapsed(false)}
          className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
          title="Expand legend"
          aria-label="Expand legend panel"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col p-4 bg-background border border-border rounded-xl text-xs text-foreground w-full lg:w-56 flex-shrink-0 shadow-md max-h-[calc(100vh-340px)] overflow-y-auto">
      <div className="flex items-center justify-between border-b border-border pb-2.5 mb-3">
        <h3 className="font-bold text-sm text-foreground">
          Graph Legend
        </h3>
        <button
          onClick={() => setCollapsed(true)}
          className="p-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
          title="Collapse legend"
          aria-label="Collapse legend panel"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
      </div>

      {/* Node Types section */}
      <div className="space-y-2">
        <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block">
          Node Types
        </span>
        <div className="space-y-1">
          {NODE_LEGEND_ITEMS.map(({ label, icon: Icon, color }) => (
            <div key={label} className="flex items-center gap-2 text-[11px] text-foreground">
              <div className={`p-1 rounded-md border border-white/5 ${color}`}>
                <Icon className="w-3 h-3" />
              </div>
              <span>{label}</span>
            </div>
          ))}
        </div>

        {/* Relationships section */}
        <div className="space-y-2 pt-3 mt-3 border-t border-border">
        <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block">
            Relationships
          </span>
          <div className="space-y-1.5">
            {REL_LEGEND_ITEMS.map(({ label, color }) => (
              <div key={label} className="flex items-center gap-2 text-[11px] font-mono font-medium">
                <ArrowRight className="w-3 h-3" style={{ color }} />
                <span className="text-foreground">{label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Bottom toggle: Show labels & Collapse */}
      <div className="pt-3 mt-3 border-t border-border space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-[11px] text-foreground font-medium">Show labels</span>
          <button
            type="button"
            role="switch"
            aria-checked={showLabels}
            onClick={() => onToggleShowLabels(!showLabels)}
            className={`relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background ${
              showLabels ? "bg-primary" : "bg-border"
            }`}
          >
            <span
              className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                showLabels ? "translate-x-4" : "translate-x-0"
              }`}
            />
          </button>
        </div>
        <button
          onClick={() => setCollapsed(true)}
          className="w-full flex items-center justify-center gap-1 py-1 text-[10px] text-muted-foreground hover:text-foreground transition-colors rounded-md hover:bg-accent"
          aria-label="Collapse legend panel"
        >
          <ChevronLeft className="w-3 h-3" />
          Collapse
        </button>
      </div>
    </div>
  );
}
