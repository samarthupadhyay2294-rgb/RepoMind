import React from "react";
import { Search, X, Maximize2, RotateCcw, EyeOff, ChevronDown } from "lucide-react";

export const REL_TYPES = [
  "Imports",
  "Calls",
  "References",
  "Inherits",
  "Implements",
  "Uses Type",
];

export const NODE_TYPES = [
  "Files",
  "Directories",
  "Modules",
  "Classes",
  "Functions",
  "Methods",
];

interface GraphToolbarProps {
  searchQuery: string;
  onSearchChange: (q: string) => void;
  relFilter: string[];
  onToggleRelFilter: (r: string) => void;
  onClearRelFilters: () => void;
  nodeFilter: string[];
  onToggleNodeFilter: (t: string) => void;
  onClearNodeFilters: () => void;
  depth: number;
  onDepthChange: (d: number) => void;
  onFitView: () => void;
  onReset: () => void;
  hasActiveFocus: boolean;
  onClearFocus: () => void;
}

export function GraphToolbar({
  searchQuery,
  onSearchChange,
  relFilter,
  onToggleRelFilter,
  onClearRelFilters,
  nodeFilter,
  onToggleNodeFilter,
  onClearNodeFilters,
  depth,
  onDepthChange,
  onFitView,
  onReset,
  hasActiveFocus,
  onClearFocus,
}: GraphToolbarProps) {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-background p-3 shadow-md text-xs text-foreground">
      {/* Search Input */}
      <div className="relative flex-1 min-w-[220px] max-w-xs">
        <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search files, symbols, or paths..."
          className="w-full rounded-lg border border-border bg-background pl-9 pr-8 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/50 transition-all font-mono"
          aria-label="Search files, symbols, or paths"
        />
        {searchQuery && (
          <button
            onClick={() => onSearchChange("")}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
            aria-label="Clear search input"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* Separator */}
      <div className="hidden sm:block w-px h-6 bg-border" />

      {/* Relationships Pills */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Rel</span>
        <button
          onClick={onClearRelFilters}
          className={`px-2 py-1 rounded-md text-[10px] font-semibold transition-colors ${
            relFilter.length === 0
              ? "bg-primary text-foreground"
              : "bg-accent text-foreground border border-border hover:bg-border"
          }`}
        >
          All
        </button>
        {REL_TYPES.map((r) => {
          const active = relFilter.includes(r.toLowerCase().replace(" ", "_"));
          return (
            <button
              key={r}
              onClick={() => onToggleRelFilter(r.toLowerCase().replace(" ", "_"))}
              aria-pressed={active}
              className={`px-2 py-1 rounded-md text-[10px] font-semibold transition-colors ${
                active
                  ? "bg-primary text-foreground"
                  : "bg-accent text-foreground border border-border hover:bg-border"
              }`}
            >
              {r}
            </button>
          );
        })}
      </div>

      {/* Separator */}
      <div className="hidden sm:block w-px h-6 bg-border" />

      {/* Node Types Pills */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Nodes</span>
        <button
          onClick={onClearNodeFilters}
          className={`px-2 py-1 rounded-md text-[10px] font-semibold transition-colors ${
            nodeFilter.length === 0
              ? "bg-primary text-foreground"
              : "bg-accent text-foreground border border-border hover:bg-border"
          }`}
        >
          All
        </button>
        {NODE_TYPES.map((t) => {
          const singular = t.toLowerCase().replace(/s$/, "");
          const active = nodeFilter.includes(singular);
          return (
            <button
              key={t}
              onClick={() => onToggleNodeFilter(singular)}
              aria-pressed={active}
              className={`px-2 py-1 rounded-md text-[10px] font-semibold transition-colors ${
                active
                  ? "bg-primary text-foreground"
                  : "bg-accent text-foreground border border-border hover:bg-border"
              }`}
            >
              {t}
            </button>
          );
        })}
      </div>

      {/* Separator */}
      <div className="hidden sm:block w-px h-6 bg-border" />

      {/* Depth Dropdown & Controls */}
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-1.5 bg-accent border border-border px-2.5 py-1.5 rounded-lg">
          <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Depth</span>
          <select
            value={depth}
            onChange={(e) => onDepthChange(Number(e.target.value))}
            className="bg-transparent text-xs font-bold text-foreground focus:outline-none cursor-pointer"
            aria-label="Traversal depth"
          >
            {[1, 2, 3].map((d) => (
              <option key={d} value={d} className="bg-background text-foreground">
                {d}
              </option>
            ))}
          </select>
          <ChevronDown className="w-3.5 h-3.5 text-muted-foreground pointer-events-none" />
        </div>

        <button
          onClick={onFitView}
          className="p-2 rounded-lg bg-accent border border-border text-foreground hover:bg-border hover:text-foreground transition-colors"
          title="Fit graph to viewport"
          aria-label="Fit graph"
        >
          <Maximize2 className="w-3.5 h-3.5" />
        </button>

        <button
          onClick={onReset}
          className="p-2 rounded-lg bg-accent border border-border text-foreground hover:bg-border hover:text-foreground transition-colors"
          title="Reset layout and zoom"
          aria-label="Reset view"
        >
          <RotateCcw className="w-3.5 h-3.5" />
        </button>

        {hasActiveFocus && (
          <button
            onClick={onClearFocus}
            className="flex items-center gap-1 px-2 py-1.5 rounded-lg border border-primary/30 text-primary hover:bg-primary/10 transition-colors text-[10px] font-semibold"
            title="Clear focus"
            aria-label="Clear focus"
          >
            <EyeOff className="w-3.5 h-3.5" />
            Clear
          </button>
        )}
      </div>
    </div>
  );
}
