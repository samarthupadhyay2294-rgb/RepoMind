"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  ChevronDown,
  ChevronRight,
  FileCode,
  GitBranch,
  Layers,
  ListTree,
  Loader2,
  Network,
  RefreshCw,
  Rocket,
  Shield,
  AlertCircle,
  CheckCircle2,
  HelpCircle,
  Workflow,
  Zap,
} from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { TooltipProvider } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { ApiError, generateOverview, getOverview } from "@/lib/api";
import type {
  OverviewComponent,
  RepositoryOverview,
} from "@/lib/overview-types";

const COMPONENT_ICONS: Record<string, typeof Layers> = {
  service: Layers,
  module: Layers,
  router: Network,
  api: Network,
  controller: Network,
  database: FileCode,
  model: FileCode,
  view: BookOpen,
  component: BookOpen,
  utility: Zap,
  config: Shield,
  test: Shield,
  migration: FileCode,
};

function componentIcon(type: string): typeof Layers {
  const t = type.toLowerCase();
  for (const [key, Icon] of Object.entries(COMPONENT_ICONS)) {
    if (t.includes(key)) return Icon;
  }
  return Layers;
}

function ConfidenceBadge({ value }: { value: string }) {
  const variant =
    value === "confirmed"
      ? "default"
      : value === "candidate"
        ? "secondary"
        : "outline";
  return <Badge variant={variant}>{value}</Badge>;
}

function EvidenceCount({ count }: { count: number }) {
  if (count === 0) return <span className="text-muted-foreground">No evidence</span>;
  return (
    <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
      <CheckCircle2 className="w-3 h-3 text-success" />
      {count} source{count === 1 ? "" : "s"}
    </span>
  );
}

function MetaBadges({
  data,
  onCopySnapshotId,
}: {
  data: RepositoryOverview;
  onCopySnapshotId: () => void;
}) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <Badge variant="outline" className="font-mono text-[11px] h-5">
        <span title={data.snapshot_id} className="cursor-pointer" onClick={onCopySnapshotId}>
          snap {data.snapshot_id.slice(0, 8)}
        </span>
        {data.snapshot_active ? (
          <span className="text-success ml-1">active</span>
        ) : (
          <span className="text-warning ml-1">pinned</span>
        )}
      </Badge>
      <Badge variant="outline" className="text-[11px] h-5">
        {new Date(data.generated_at).toLocaleDateString("en-US", {
          month: "short",
          day: "numeric",
          year: "numeric",
        })}
      </Badge>
      <Badge variant="outline" className="text-[11px] h-5 font-mono">
        {data.generation_model}
      </Badge>
      {data.truncated && (
        <Badge variant="secondary" className="text-[11px] h-5">
          evidence truncated
        </Badge>
      )}
    </div>
  );
}

function SectionHeading({
  icon: Icon,
  children,
  count,
}: {
  icon: typeof Layers;
  children: React.ReactNode;
  count?: number;
}) {
  return (
    <h2 className="text-[22px] font-bold tracking-tight text-foreground flex items-center gap-2.5 mb-1">
      <span className="flex items-center justify-center w-7 h-7 rounded-lg bg-primary/15 text-primary">
        <Icon className="w-4 h-4" />
      </span>
      {children}
      {count !== undefined && (
        <span className="text-[13px] font-normal text-muted-foreground">
          ({count})
        </span>
      )}
    </h2>
  );
}

function OverviewSkeleton() {
  return (
    <div className="space-y-8" role="status" aria-label="Loading overview">
      <div className="space-y-3">
        <Skeleton className="h-5 w-48 bg-muted" />
        <Skeleton className="h-8 w-80 bg-muted" />
      </div>
      <Skeleton className="h-56 w-full rounded-xl bg-muted" />
      <div className="space-y-3">
        <Skeleton className="h-5 w-36 bg-muted" />
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-32 rounded-xl bg-muted" />
          ))}
        </div>
      </div>
      <div className="space-y-3">
        <Skeleton className="h-5 w-28 bg-muted" />
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-16 rounded-lg bg-muted" />
          ))}
        </div>
      </div>
    </div>
  );
}

function DisabledBanner() {
  return (
    <div
      className="rounded-xl border border-warning/30 bg-warning/10 p-4 text-sm text-warning flex items-start gap-3"
      role="alert"
    >
      <AlertCircle className="w-5 h-5 text-warning flex-shrink-0 mt-0.5" />
      <div>
        <p className="font-semibold">Repository overviews are disabled for this deployment.</p>
        <p className="text-warning/80 mt-1">
          Chat and retrieval remain available. To enable locally, set{" "}
          <code className="bg-warning/20 px-1 py-0.5 rounded text-[12px] font-mono">
            ARCHITECTURE_OVERVIEW=true
          </code>{" "}
          in{" "}
          <code className="bg-warning/20 px-1 py-0.5 rounded text-[12px] font-mono">
            backend/.env
          </code>{" "}
          and restart the backend, then open an indexed repository and choose Generate.
        </p>
      </div>
    </div>
  );
}

function ErrorBanner({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div
      className="rounded-xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive flex items-start justify-between gap-4"
      role="alert"
    >
      <div className="flex items-start gap-2">
        <AlertCircle className="w-4 h-4 text-destructive flex-shrink-0 mt-0.5" />
        <span>{message}</span>
      </div>
      <Button
        variant="outline"
        size="sm"
        className="h-7 border-destructive/30 bg-destructive/20 text-destructive hover:bg-destructive/20 text-xs gap-1.5 flex-shrink-0"
        onClick={onRetry}
      >
        <RefreshCw className="w-3.5 h-3.5" />
        Retry
      </Button>
    </div>
  );
}

function NotIndexedCard({ repositoryId }: { repositoryId: string }) {
  return (
    <div className="rounded-xl border border-border bg-background p-8 text-center space-y-4">
      <div className="flex justify-center">
        <div className="p-3 rounded-full bg-warning/15 text-warning">
          <AlertCircle className="w-8 h-8" />
        </div>
      </div>
      <div>
        <h2 className="text-[20px] font-bold text-foreground">Repository Not Indexed</h2>
        <p className="text-[14px] text-muted-foreground mt-2 max-w-md mx-auto leading-relaxed">
          This repository must be indexed before an architecture overview can be generated. Please index the repository first.
        </p>
      </div>
      <Link href={`/repositories/${repositoryId}`}>
        <Button className="h-9 px-5">
          <GitBranch className="mr-2 h-4 w-4" />
          View Repository Details
        </Button>
      </Link>
    </div>
  );
}

function NotFoundCard({ onGenerate, generating }: { onGenerate: () => void; generating: boolean }) {
  return (
    <div className="rounded-xl border border-border bg-background p-8 text-center space-y-4">
      <div className="flex justify-center">
        <div className="p-3 rounded-full bg-primary/15 text-primary">
          <Layers className="w-8 h-8" />
        </div>
      </div>
      <div>
        <h2 className="text-[20px] font-bold text-foreground">No overview yet</h2>
        <p className="text-[14px] text-muted-foreground mt-2 max-w-md mx-auto leading-relaxed">
          This repository has been indexed but has no architecture overview. Generate one
          to get a grounded briefing of its components, entry points, and data flows.
        </p>
      </div>
      <Button
        onClick={onGenerate}
        disabled={generating}
        className="h-9 px-5"
      >
        {generating ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Rocket className="mr-2 h-4 w-4" />}
        {generating ? "Generating\u2026" : "Generate overview"}
      </Button>
    </div>
  );
}

function StaleBanner({ onRegenerate, generating }: { onRegenerate: () => void; generating: boolean }) {
  return (
    <div
      className="rounded-xl border border-warning/30 bg-warning/10 p-3 text-sm text-warning flex items-center gap-2"
      role="status"
    >
      <AlertCircle className="w-4 h-4 text-warning flex-shrink-0" />
      <span>
        Overview is from an older snapshot.{" "}
        <button
          className="underline underline-offset-2 hover:text-warning transition-colors"
          onClick={onRegenerate}
          disabled={generating}
        >
          Regenerate for the current snapshot
        </button>
      </span>
    </div>
  );
}

/* ────────────────── Architecture Map ────────────────── */

const TYPE_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  service: { bg: "bg-primary/10", text: "text-primary", border: "border-primary/30" },
  router: { bg: "bg-primary/10", text: "text-primary", border: "border-primary/30" },
  api: { bg: "bg-primary/10", text: "text-primary", border: "border-primary/30" },
  controller: { bg: "bg-primary/10", text: "text-primary", border: "border-primary/30" },
  database: { bg: "bg-warning/10", text: "text-warning", border: "border-warning/30" },
  model: { bg: "bg-warning/10", text: "text-warning", border: "border-warning/30" },
  config: { bg: "bg-destructive/10", text: "text-destructive", border: "border-destructive/30" },
  component: { bg: "bg-success/10", text: "text-success", border: "border-success/30" },
  view: { bg: "bg-success/10", text: "text-success", border: "border-success/30" },
  utility: { bg: "bg-muted-foreground/10", text: "text-foreground", border: "border-muted-foreground/30" },
  module: { bg: "bg-primary/10", text: "text-primary", border: "border-primary/30" },
};

function typeColor(type: string) {
  const t = type.toLowerCase();
  for (const [key, color] of Object.entries(TYPE_COLORS)) {
    if (t.includes(key)) return color;
  }
  return { bg: "bg-muted-foreground/10", text: "text-muted-foreground", border: "border-muted-foreground/30" };
}

function ArchitectureMap({
  components,
  flows,
  selected,
  onSelect,
}: {
  components: OverviewComponent[];
  flows: { source: string; target: string; description: string }[];
  selected: string | null;
  onSelect: (id: string | null) => void;
}) {
  if (!components.length) {
    return (
      <p className="text-[14px] text-muted-foreground py-8 text-center">
        No components to display in the map.
      </p>
    );
  }

  const byName = new Map(components.map((c) => [c.name, c]));
  const byId = new Map(components.map((c) => [c.id, c]));
  const resolve = (ref: string) => byId.get(ref) ?? byName.get(ref);

  const W = 240;
  const H = 100;
  const GAP = 36;
  const PAD = 20;
  const width = components.length * (W + GAP) - GAP + PAD * 2;
  const height = H + PAD * 2 + 36;

  return (
    <div className="overflow-x-auto -mx-1 px-1 pb-2">
      <svg
        width={Math.max(width, 600)}
        viewBox={`0 0 ${Math.max(width, 600)} ${height}`}
        role="img"
        aria-label={`Architecture map: ${components.length} component${components.length === 1 ? "" : "s"}, ${flows.length} flow${flows.length === 1 ? "" : "s"}`}
        className="min-w-[600px]"
      >
        <defs>
          <style>{`g[role=button]:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; border-radius: 10px; }`}</style>
          <marker id="ov-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
            <path d="M0,0 L8,4 L0,8" fill="none" stroke="var(--muted-foreground)" strokeWidth="1.5" />
          </marker>
        </defs>

        {flows.map((f, i) => {
          const a = resolve(f.source);
          const b = resolve(f.target);
          if (!a || !b) return null;
          const ai = components.indexOf(a);
          const bi = components.indexOf(b);
          if (ai < 0 || bi < 0) return null;
          const x1 = PAD + ai * (W + GAP) + W;
          const x2 = PAD + bi * (W + GAP);
          const y = PAD + H / 2;
          if (x2 <= x1) return null;
          return (
            <g key={i}>
              <line
                x1={x1}
                y1={y}
                x2={x2}
                y2={y}
                stroke="var(--muted-foreground)"
                strokeWidth="1.5"
                strokeDasharray="4,3"
                markerEnd="url(#ov-arrow)"
                opacity="0.7"
              />
              <text
                x={(x1 + x2) / 2}
                y={y - 8}
                fontSize="10"
                textAnchor="middle"
                fill="var(--muted-foreground)"
              >
                {f.description.length > 32
                  ? f.description.slice(0, 32) + "\u2026"
                  : f.description}
              </text>
            </g>
          );
        })}

        {components.map((c, i) => {
          const x = PAD + i * (W + GAP);
          const y = PAD;
          const isSelected = selected === c.id;
          const colors = typeColor(c.type);
          return (
            <g
              key={c.id}
              onClick={() => onSelect(isSelected ? null : c.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect(isSelected ? null : c.id);
                }
              }}
              style={{ cursor: "pointer" }}
              role="button"
              tabIndex={0}
              aria-label={`${c.name} (${c.type})`}
              aria-pressed={isSelected}
            >
              <rect
                x={x}
                y={y}
                width={W}
                height={H}
                rx={10}
                fill={isSelected ? "var(--primary)" : "var(--background)"}
                stroke={isSelected ? "var(--primary)" : "var(--border)"}
                strokeWidth={isSelected ? 2 : 1.5}
                className="transition-colors"
              />
              <rect
                x={x}
                y={y}
                width={W}
                height={4}
                rx={2}
                fill={isSelected ? "var(--primary)" : colors.text}
                opacity={isSelected ? 1 : 0.5}
              />
              <text x={x + 14} y={y + 28} fontSize="14" fontWeight="600" fill="var(--foreground)">
                {c.name.length > 28 ? c.name.slice(0, 28) + "\u2026" : c.name}
              </text>
              <text x={x + 14} y={y + 46} fontSize="11" fill={colors.text}>
                {c.type}
              </text>
              <text x={x + 14} y={y + 66} fontSize="11" fill="var(--muted-foreground)">
                {c.paths.length} path{c.paths.length === 1 ? "" : "s"}
              </text>
              <text x={x + 14} y={y + 82} fontSize="11" fill="var(--muted-foreground)">
                {c.evidence_ids.length} evidence{c.evidence_ids.length === 1 ? "" : ""}
              </text>
              {isSelected && (
                <circle cx={x + W - 14} cy={y + 14} r={4} fill="var(--primary)" />
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function ComponentInspector({
  component,
  repositoryId,
  onClose,
}: {
  component: OverviewComponent;
  repositoryId: string;
  onClose: () => void;
}) {
  const colors = typeColor(component.type);
  return (
    <div
      className="rounded-xl border border-border bg-background p-5 space-y-3"
      role="complementary"
      aria-label={`Details for ${component.name}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <h3 className="text-[16px] font-bold text-foreground">{component.name}</h3>
          <Badge variant="outline" className={cn("text-[11px] h-5", colors.text)}>
            {component.type}
          </Badge>
        </div>
        <button
          onClick={onClose}
          className="text-muted-foreground hover:text-foreground transition-colors p-1 -m-1 rounded"
          aria-label="Close inspector"
        >
          <ChevronDown className="w-4 h-4" />
        </button>
      </div>

      <p className="text-[14px] text-foreground leading-relaxed">
        {component.description}
      </p>

      {component.responsibilities.length > 0 && (
        <div className="space-y-1">
          <p className="text-[12px] font-semibold text-muted-foreground uppercase tracking-wider">Responsibilities</p>
          <ul className="space-y-1">
            {component.responsibilities.map((r, i) => (
              <li key={i} className="text-[13px] text-foreground flex items-start gap-2">
                <span className="text-primary mt-1.5 text-[8px]">&#9679;</span>
                {r}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="space-y-1">
        <p className="text-[12px] font-semibold text-muted-foreground uppercase tracking-wider">Paths</p>
        <div className="flex flex-wrap gap-1.5">
          {component.paths.map((p) => (
            <code
              key={p}
              className="text-[12px] font-mono text-primary bg-primary/10 px-2 py-0.5 rounded"
            >
              {p}
            </code>
          ))}
        </div>
      </div>

      <div className="flex items-center justify-between">
        <EvidenceCount count={component.evidence_ids.length} />
        <Link
          href={`/repositories/${repositoryId}/graph`}
          className="text-[13px] text-primary hover:text-primary transition-colors flex items-center gap-1"
        >
          <GitBranch className="w-3.5 h-3.5" />
          Explore dependencies
        </Link>
      </div>
    </div>
  );
}

/* ────────────────── Main Page ────────────────── */

export default function OverviewPage() {
  const params = useParams();
  const id = params.id as string;

  const [data, setData] = useState<RepositoryOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [notIndexed, setNotIndexed] = useState(false);
  const [disabled, setDisabled] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [evidenceExpanded, setEvidenceExpanded] = useState(false);

  async function fetchOverview() {
    setLoading(true);
    setError(null);
    setNotFound(false);
    setNotIndexed(false);
    setDisabled(false);
    try {
      const ov = await getOverview(id);
      setData(ov);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.code === "OVERVIEW_NOT_FOUND" || err.status === 404) {
          setNotFound(true);
        } else if (err.code === "REPOSITORY_NOT_INDEXED") {
          setNotIndexed(true);
        } else if (err.code === "OVERVIEW_DISABLED" || err.status === 403) {
          setDisabled(true);
        } else {
          setError(err.message);
        }
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to load overview.");
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const ov = await getOverview(id);
        if (!cancelled) setData(ov);
      } catch (err: unknown) {
        if (cancelled) return;
        if (err instanceof ApiError) {
          if (err.code === "OVERVIEW_NOT_FOUND" || err.status === 404) {
            setNotFound(true);
          } else if (err.code === "REPOSITORY_NOT_INDEXED") {
            setNotIndexed(true);
          } else if (err.code === "OVERVIEW_DISABLED" || err.status === 403) {
            setDisabled(true);
          } else {
            setError(err.message);
          }
        } else if (err instanceof Error) {
          setError(err.message);
        } else {
          setError("Failed to load overview.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [id]);

  async function handleGenerate() {
    setGenerating(true);
    setError(null);
    try {
      const ov = await generateOverview(id);
      setData(ov);
      setNotFound(false);
      setNotIndexed(false);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.code === "REPOSITORY_NOT_INDEXED") {
          setNotIndexed(true);
        } else if (err.code === "OVERVIEW_DISABLED" || err.status === 403) {
          setDisabled(true);
        } else {
          setError(err.message);
        }
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Generation failed.");
      }
    } finally {
      setGenerating(false);
    }
  }

  const selectedComponent =
    data?.overview.components.find((c) => c.id === selected) ?? null;

  return (
    <AppShell>
      <TooltipProvider>
        <div className="mx-auto max-w-6xl p-4 sm:p-6 lg:p-8 space-y-8">
          {/* ── Breadcrumb ── */}
          <nav className="flex items-center gap-2 text-[13px] text-muted-foreground" aria-label="Breadcrumb">
            <Link
              href="/"
              className="font-bold text-foreground hover:text-primary transition-colors"
            >
              RepoMind
            </Link>
            <ChevronRight className="w-3.5 h-3.5 text-muted-foreground/40" aria-hidden="true" />
            <span className="text-muted-foreground/50">Repositories</span>
            <ChevronRight className="w-3.5 h-3.5 text-muted-foreground/40" aria-hidden="true" />
            <Link
              href={`/repositories/${id}`}
              className="text-foreground font-semibold hover:text-primary transition-colors"
            >
              {id.slice(0, 8)}
            </Link>
            <ChevronRight className="w-3.5 h-3.5 text-muted-foreground/40" aria-hidden="true" />
            <span className="text-foreground font-medium">Overview</span>
          </nav>

          {/* ── Header ── */}
          <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
            <div className="space-y-2">
              <h1 className="text-[28px] sm:text-[32px] font-bold tracking-tight text-foreground leading-tight">
                Architecture Overview
              </h1>
              <p className="text-[14px] text-muted-foreground leading-relaxed max-w-lg">
                Evidence-grounded briefing of this repository&apos;s structure, components, and data flows.
              </p>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <Link href={`/repositories/${id}/graph`}>
                <Button variant="outline" size="sm" className="h-8 text-[13px]">
                  <GitBranch className="w-3.5 h-3.5 mr-1.5" />
                  Dependency graph
                </Button>
              </Link>
              <Button
                size="sm"
                onClick={data ? handleGenerate : fetchOverview}
                disabled={generating || loading}
                className="h-8 text-[13px]"
              >
                {generating ? (
                  <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                ) : (
                  <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
                )}
                {data ? "Regenerate" : "Retry"}
              </Button>
            </div>
          </div>

          {/* ── Status banners ── */}
          {disabled && <DisabledBanner />}
          {error && <ErrorBanner message={error} onRetry={fetchOverview} />}

          {/* ── Loading skeleton ── */}
          {loading && !data && !disabled && !notFound && !notIndexed && <OverviewSkeleton />}

          {/* ── Not Indexed ── */}
          {notIndexed && !loading && <NotIndexedCard repositoryId={id} />}

          {/* ── Not found ── */}
          {notFound && !loading && !notIndexed && (
            <NotFoundCard onGenerate={handleGenerate} generating={generating} />
          )}

          {/* ── Content ── */}
          {data && (
            <div className="space-y-8">
              {/* Meta badges */}
              <MetaBadges data={data} onCopySnapshotId={() => navigator.clipboard.writeText(data.snapshot_id)} />

              {!data.snapshot_active && (
                <StaleBanner onRegenerate={handleGenerate} generating={generating} />
              )}

              {/* ── Summary ── */}
              <section aria-labelledby="summary-heading">
                <SectionHeading icon={BookOpen}>Summary</SectionHeading>
                <div className="mt-3 rounded-xl border border-border bg-background p-6 sm:p-8">
                  <p className="text-[18px] leading-[1.7] text-foreground">
                    {data.overview.summary}
                  </p>
                  <div className="mt-4 flex items-center gap-3 flex-wrap">
                    {data.overview.architecture_style && (
                      <Badge variant="secondary" className="text-[12px] h-6 px-3">
                        {data.overview.architecture_style}
                      </Badge>
                    )}
                    <span className="text-[13px] text-muted-foreground">
                      {data.overview.components.length} component{data.overview.components.length === 1 ? "" : "s"}
                      {" \u00b7 "}
                      {data.overview.entry_points.length} entry point{data.overview.entry_points.length === 1 ? "" : "s"}
                      {" \u00b7 "}
                      {data.overview.data_flows.length} data flow{data.overview.data_flows.length === 1 ? "" : "s"}
                    </span>
                  </div>
                </div>
              </section>

              {/* ── Architecture Map ── */}
              <section aria-labelledby="map-heading">
                <SectionHeading icon={Network}>Architecture Map</SectionHeading>
                <div className="mt-3 rounded-xl border border-border bg-background p-4 sm:p-6">
                  <ArchitectureMap
                    components={data.overview.components}
                    flows={data.overview.data_flows}
                    selected={selected}
                    onSelect={setSelected}
                  />
                  {selectedComponent && (
                    <div className="mt-4">
                      <ComponentInspector
                        component={selectedComponent}
                        repositoryId={id}
                        onClose={() => setSelected(null)}
                      />
                    </div>
                  )}

                  {/* Accessible text alternative */}
                  <details className="mt-4 group">
                    <summary className="text-[13px] text-muted-foreground cursor-pointer hover:text-muted-foreground transition-colors">
                      Text alternative for screen readers
                    </summary>
                    <div className="mt-3 space-y-2 text-[13px] text-foreground">
                      <p>
                        {data.overview.components.length} components, {data.overview.data_flows.length} data flows.
                      </p>
                      <ul className="space-y-1 list-disc ml-5">
                        {data.overview.components.map((c) => (
                          <li key={c.id}>
                            <strong>{c.name}</strong> ({c.type}): {c.description.slice(0, 120)}
                            {c.description.length > 120 ? "\u2026" : ""}
                          </li>
                        ))}
                      </ul>
                      {data.overview.data_flows.length > 0 && (
                        <ul className="space-y-1 list-disc ml-5">
                          {data.overview.data_flows.map((f, i) => (
                            <li key={i}>
                              {f.source} &rarr; {f.target}: {f.description}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </details>
                </div>
              </section>

              {/* ── Entry Points ── */}
              {data.overview.entry_points.length > 0 && (
                <section aria-labelledby="entrypoints-heading">
                  <SectionHeading icon={Rocket} count={data.overview.entry_points.length}>
                    Entry Points
                  </SectionHeading>
                  <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
                    {data.overview.entry_points.map((ep, i) => (
                      <div
                        key={i}
                        className="rounded-xl border border-border bg-background p-4 space-y-2 hover:border-primary/40 transition-colors"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <h3 className="text-[15px] font-semibold text-foreground">
                            {ep.name}
                          </h3>
                          <ConfidenceBadge value={ep.confidence} />
                        </div>
                        <div className="flex items-center gap-2 text-[12px] text-muted-foreground">
                          <Badge variant="outline" className="text-[11px] h-5 font-mono">
                            {ep.type}
                          </Badge>
                          <span className="font-mono text-muted-foreground">
                            {ep.path}:{ep.start_line}
                          </span>
                        </div>
                        {ep.description && (
                          <p className="text-[13px] text-foreground leading-relaxed">
                            {ep.description}
                          </p>
                        )}
                        <EvidenceCount count={ep.evidence_ids.length} />
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* ── Components ── */}
              {data.overview.components.length > 0 && (
                <section aria-labelledby="components-heading">
                  <SectionHeading icon={Layers} count={data.overview.components.length}>
                    Components
                  </SectionHeading>
                  <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {data.overview.components.map((c) => {
                      const Icon = componentIcon(c.type);
                      const colors = typeColor(c.type);
                      const isExpanded = selected === c.id;
                      return (
                        <div
                          key={c.id}
                          className={cn(
                            "rounded-xl border bg-background p-4 space-y-2 transition-colors cursor-pointer",
                            isExpanded
                              ? "border-primary/60"
                              : "border-border hover:border-primary/30"
                          )}
                          onClick={() => setSelected(isExpanded ? null : c.id)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              setSelected(isExpanded ? null : c.id);
                            }
                          }}
                          role="button"
                          tabIndex={0}
                          aria-label={`${c.name} (${c.type})`}
                          aria-expanded={isExpanded}
                        >
                          <div className="flex items-center gap-2">
                            <span
                              className={cn(
                                "flex items-center justify-center w-7 h-7 rounded-lg",
                                colors.bg
                              )}
                            >
                              <Icon className={cn("w-3.5 h-3.5", colors.text)} />
                            </span>
                            <div className="flex-1 min-w-0">
                              <h3 className="text-[14px] font-semibold text-foreground truncate">
                                {c.name}
                              </h3>
                              <span className={cn("text-[11px]", colors.text)}>
                                {c.type}
                              </span>
                            </div>
                          </div>

                          <p className="text-[13px] text-foreground leading-relaxed line-clamp-3">
                            {c.description}
                          </p>

                          <div className="flex flex-wrap gap-1">
                            {c.paths.slice(0, 2).map((p) => (
                              <code
                                key={p}
                                className="text-[11px] font-mono text-muted-foreground bg-muted px-1.5 py-0.5 rounded"
                              >
                                {p.length > 28 ? p.slice(0, 28) + "\u2026" : p}
                              </code>
                            ))}
                            {c.paths.length > 2 && (
                              <span className="text-[11px] text-muted-foreground">
                                +{c.paths.length - 2} more
                              </span>
                            )}
                          </div>

                          <EvidenceCount count={c.evidence_ids.length} />
                        </div>
                      );
                    })}
                  </div>
                </section>
              )}

              {/* ── Data Flows ── */}
              {data.overview.data_flows.length > 0 && (
                <section aria-labelledby="flows-heading">
                  <SectionHeading icon={Workflow} count={data.overview.data_flows.length}>
                    Data Flows
                  </SectionHeading>
                  <div className="mt-3 space-y-2">
                    {data.overview.data_flows.map((f, i) => (
                      <div
                        key={i}
                        className="rounded-xl border border-border bg-background p-4 flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4"
                      >
                        <div className="flex items-center gap-2 flex-shrink-0 min-w-0">
                          <code className="text-[13px] font-mono text-primary bg-primary/10 px-2 py-1 rounded">
                            {f.source}
                          </code>
                          <ArrowRight className="w-4 h-4 text-muted-foreground flex-shrink-0" aria-hidden="true" />
                          <code className="text-[13px] font-mono text-primary bg-primary/10 px-2 py-1 rounded">
                            {f.target}
                          </code>
                        </div>
                        <p className="text-[13px] text-foreground leading-relaxed">
                          {f.description}
                        </p>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* ── Key Dependencies + Configuration (side by side) ── */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Key Dependencies */}
                <section aria-labelledby="deps-heading">
                  <SectionHeading icon={Zap} count={data.overview.key_dependencies.length}>
                    Key Dependencies
                  </SectionHeading>
                  <div className="mt-3 space-y-2">
                    {data.overview.key_dependencies.length === 0 && (
                      <p className="text-[14px] text-muted-foreground">None identified.</p>
                    )}
                    {data.overview.key_dependencies.map((d, i) => (
                      <div
                        key={i}
                        className="rounded-lg border border-border bg-background p-3 flex items-start gap-3"
                      >
                        <span className="flex items-center justify-center w-6 h-6 rounded bg-warning/10 flex-shrink-0 mt-0.5">
                          <Zap className="w-3 h-3 text-warning" />
                        </span>
                        <div className="min-w-0">
                          <p className="text-[14px] font-semibold text-foreground">{d.name}</p>
                          {d.purpose && (
                            <p className="text-[13px] text-muted-foreground leading-relaxed mt-0.5">
                              {d.purpose}
                            </p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>

                {/* Configuration */}
                <section aria-labelledby="config-heading">
                  <SectionHeading icon={Shield} count={data.overview.configuration_areas.length}>
                    Configuration
                  </SectionHeading>
                  <div className="mt-3 space-y-2">
                    {data.overview.configuration_areas.length === 0 && (
                      <p className="text-[14px] text-muted-foreground">None identified.</p>
                    )}
                    {data.overview.configuration_areas.map((c, i) => (
                      <div
                        key={i}
                        className="rounded-lg border border-border bg-background p-3 flex items-start gap-3"
                      >
                        <span className="flex items-center justify-center w-6 h-6 rounded bg-destructive/10 flex-shrink-0 mt-0.5">
                          <Shield className="w-3 h-3 text-destructive" />
                        </span>
                        <div className="min-w-0">
                          <code className="text-[13px] font-mono text-foreground">{c.path}</code>
                          {c.description && (
                            <p className="text-[13px] text-muted-foreground leading-relaxed mt-0.5">
                              {c.description}
                            </p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              </div>

              {/* ── Boundaries ── */}
              {data.overview.boundaries.length > 0 && (
                <section aria-labelledby="boundaries-heading">
                  <SectionHeading icon={Shield} count={data.overview.boundaries.length}>
                    Boundaries
                  </SectionHeading>
                  <div className="mt-3 space-y-2">
                    {data.overview.boundaries.map((b, i) => (
                      <div
                        key={i}
                        className="rounded-xl border border-border bg-background p-4"
                      >
                        <h3 className="text-[15px] font-semibold text-foreground">{b.name}</h3>
                        <p className="text-[13px] text-foreground leading-relaxed mt-1">
                          {b.description}
                        </p>
                        {b.paths.length > 0 && (
                          <div className="flex flex-wrap gap-1.5 mt-2">
                            {b.paths.map((p) => (
                              <code
                                key={p}
                                className="text-[11px] font-mono text-muted-foreground bg-muted px-1.5 py-0.5 rounded"
                              >
                                {p}
                              </code>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* ── Uncertainties ── */}
              {data.overview.uncertainties.length > 0 && (
                <section aria-labelledby="uncertainties-heading">
                  <SectionHeading icon={HelpCircle} count={data.overview.uncertainties.length}>
                    Uncertainties
                  </SectionHeading>
                  <div className="mt-3 space-y-2">
                    {data.overview.uncertainties.map((u, i) => (
                      <div
                        key={i}
                        className="rounded-xl border border-border bg-background p-4 flex items-start gap-3"
                      >
                        <HelpCircle className="w-4 h-4 text-muted-foreground flex-shrink-0 mt-0.5" />
                        <div>
                          <p className="text-[14px] text-foreground leading-relaxed">
                            {u.statement}
                          </p>
                          {u.reason && (
                            <p className="text-[12px] text-muted-foreground mt-1">
                              {u.reason}
                            </p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* ── Evidence (collapsible) ── */}
              <section aria-labelledby="evidence-heading">
                <button
                  onClick={() => setEvidenceExpanded((prev) => !prev)}
                  className="flex items-center gap-2 text-left group"
                  aria-expanded={evidenceExpanded}
                >
                  <span className="text-[22px] font-bold tracking-tight text-foreground flex items-center gap-2.5">
                    <span className="flex items-center justify-center w-7 h-7 rounded-lg bg-primary/15 text-primary">
                      <ListTree className="w-4 h-4" />
                    </span>
                    Evidence
                  </span>
                  <Badge variant="outline" className="text-[11px] h-5 font-mono">
                    {data.evidence_items_used}/{data.evidence_items_total}
                  </Badge>
                  {evidenceExpanded ? (
                    <ChevronDown className="w-4 h-4 text-muted-foreground group-hover:text-muted-foreground transition-colors" />
                  ) : (
                    <ChevronRight className="w-4 h-4 text-muted-foreground group-hover:text-muted-foreground transition-colors" />
                  )}
                </button>
                {evidenceExpanded && (
                  <div className="mt-3 rounded-xl border border-border bg-background p-4">
                    {data.evidence.length === 0 ? (
                      <p className="text-[13px] text-muted-foreground">No evidence items.</p>
                    ) : (
                      <div className="max-h-64 overflow-auto space-y-1">
                        {data.evidence.map((e) => (
                          <div
                            key={e.id}
                            className="flex items-center gap-2 text-[12px] font-mono text-foreground py-0.5"
                          >
                            <span className="text-primary">{e.path}</span>
                            <span className="text-muted-foreground">:</span>
                            <span>{e.start_line}-{e.end_line}</span>
                            {e.redacted && (
                              <Badge variant="secondary" className="text-[10px] h-4 px-1.5">
                                redacted
                              </Badge>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </section>

              {/* ── Footer ── */}
              <Separator className="bg-muted" />
              <div className="flex gap-4 pb-8">
                <Link
                  href={`/repositories/${id}/graph`}
                  className="text-[14px] text-primary hover:text-primary transition-colors flex items-center gap-1.5"
                >
                  <GitBranch className="w-4 h-4" />
                  Open dependency graph
                </Link>
                <Link
                  href={`/repositories/${id}/chat`}
                  className="text-[14px] text-primary hover:text-primary transition-colors flex items-center gap-1.5"
                >
                  <BookOpen className="w-4 h-4" />
                  Ask in chat
                </Link>
              </div>
            </div>
          )}
        </div>
      </TooltipProvider>
    </AppShell>
  );
}
