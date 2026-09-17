"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  Clock,
  GitBranch,
  Loader2,
  RefreshCw,
  Search,
  WifiOff,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AppShell } from "@/components/layout/app-shell";
import { RepositoryCard } from "@/components/repositories/repository-card";
import { AddRepositoryDialog } from "@/components/repositories/add-repository-dialog";
import { DeleteRepositoryDialog } from "@/components/repositories/delete-repository-dialog";
import {
  ApiError,
  listRepositories,
  createRepository,
  deleteRepository,
} from "@/lib/api";
import type { Repository, RepositoryCreate } from "@/lib/types";

export default function DashboardPage() {
  const [repos, setRepos] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [search, setSearch] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<Repository | null>(null);

  const fetchRepos = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listRepositories();
      setRepos(res.items);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(err);
      } else if (err instanceof Error) {
        setError(new ApiError("API_ERROR", err.message));
      } else {
        setError(new ApiError("API_ERROR", "Failed to load repositories."));
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await listRepositories();
        if (!cancelled) setRepos(res.items);
      } catch (err: unknown) {
        if (!cancelled) {
          if (err instanceof ApiError) {
            setError(err);
          } else if (err instanceof Error) {
            setError(new ApiError("API_ERROR", err.message));
          } else {
            setError(new ApiError("API_ERROR", "Failed to load repositories."));
          }
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleAdd(data: RepositoryCreate) {
    await createRepository(data);
    await fetchRepos();
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    await deleteRepository(deleteTarget.id);
    setDeleteTarget(null);
    await fetchRepos();
  }

  async function handleReindex() {
    await fetchRepos();
  }

  const filtered = repos.filter((r) =>
    r.name.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <AppShell>
      <div className="mx-auto max-w-5xl p-4 sm:p-6 space-y-6 w-full min-w-0">
        {/* Hero Header */}
        <div className="space-y-1">
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground">
            Understand your codebase with AI
          </h1>
          <p className="text-sm sm:text-base text-muted-foreground">
            Ask questions, trace dependencies, and explore your repo.
          </p>
        </div>

        {/* Search + Add Bar */}
        <div className="flex flex-col-reverse sm:flex-row items-stretch sm:items-center justify-between gap-3 w-full">
          <div className="relative flex-1 min-w-0">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground pointer-events-none" />
            <Input
              placeholder="Search repositories..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9 w-full"
            />
          </div>
          <div className="shrink-0 flex sm:justify-end">
            <AddRepositoryDialog onAdd={handleAdd} />
          </div>
        </div>

        {/* Initial Loading */}
        {loading && (
          <div className="flex flex-col items-center justify-center py-20 space-y-3">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <p className="text-sm text-muted-foreground font-medium">Loading repositories...</p>
          </div>
        )}

        {/* Backend Unreachable */}
        {!loading && error?.code === "BACKEND_UNREACHABLE" && (
          <div className="flex flex-col items-center justify-center py-16 text-center space-y-4 rounded-xl border border-border bg-card p-8 shadow-sm">
            <div className="rounded-full bg-destructive/10 p-4 text-destructive">
              <WifiOff className="h-8 w-8" />
            </div>
            <div className="space-y-1 max-w-md">
              <h3 className="text-lg font-semibold text-foreground">Backend Server Unreachable</h3>
              <p className="text-sm text-muted-foreground">
                Unable to connect to the RepoMind backend. Please ensure the backend server is running.
              </p>
            </div>
            <Button variant="default" onClick={fetchRepos} className="gap-2">
              <RefreshCw className="h-4 w-4" />
              Retry Connection
            </Button>
          </div>
        )}

        {/* Request Timeout */}
        {!loading && error?.code === "REQUEST_TIMEOUT" && (
          <div className="flex flex-col items-center justify-center py-16 text-center space-y-4 rounded-xl border border-border bg-card p-8 shadow-sm">
            <div className="rounded-full bg-warning/10 p-4 text-warning">
              <Clock className="h-8 w-8" />
            </div>
            <div className="space-y-1 max-w-md">
              <h3 className="text-lg font-semibold text-foreground">Request Timed Out</h3>
              <p className="text-sm text-muted-foreground">
                The backend server took too long to respond. Please check your connection and try again.
              </p>
            </div>
            <Button variant="default" onClick={fetchRepos} className="gap-2">
              <RefreshCw className="h-4 w-4" />
              Retry Request
            </Button>
          </div>
        )}

        {/* API / Server Error */}
        {!loading && error && error.code !== "BACKEND_UNREACHABLE" && error.code !== "REQUEST_TIMEOUT" && (
          <div className="flex flex-col items-center justify-center py-16 text-center space-y-4 rounded-xl border border-destructive/20 bg-card p-8 shadow-sm">
            <div className="rounded-full bg-destructive/10 p-4 text-destructive">
              <AlertTriangle className="h-8 w-8" />
            </div>
            <div className="space-y-1 max-w-md">
              <h3 className="text-lg font-semibold text-foreground">Failed to Load Repositories</h3>
              <p className="text-sm text-muted-foreground">
                {error.message || "An unexpected error occurred while communicating with the server."}
              </p>
            </div>
            <Button variant="default" onClick={fetchRepos} className="gap-2">
              <RefreshCw className="h-4 w-4" />
              Retry
            </Button>
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && repos.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 text-center space-y-4 rounded-xl border border-border bg-card/50 p-8">
            <div className="rounded-full bg-muted p-4">
              <GitBranch className="h-8 w-8 text-muted-foreground" />
            </div>
            <div className="space-y-1">
              <h3 className="text-lg font-semibold text-foreground">No repositories yet</h3>
              <p className="text-sm text-muted-foreground max-w-sm">
                Connect a repository to start exploring your codebase with RepoMind.
              </p>
            </div>
            <AddRepositoryDialog onAdd={handleAdd} />
          </div>
        )}

        {/* Repository grid */}
        {!loading && !error && filtered.length > 0 && (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              {filtered.length} {filtered.length === 1 ? "repository" : "repositories"}
            </p>
            <div className="grid gap-4 grid-cols-1 sm:grid-cols-2">
              {filtered.map((repo) => (
                <RepositoryCard
                  key={repo.id}
                  repository={repo}
                  onDelete={(id) => {
                    const r = repos.find((x) => x.id === id);
                    if (r) setDeleteTarget(r);
                  }}
                  onReindex={handleReindex}
                />
              ))}
            </div>
          </div>
        )}

        {/* No search results */}
        {!loading && !error && repos.length > 0 && filtered.length === 0 && (
          <div className="text-center py-12 space-y-2">
            <p className="text-sm text-muted-foreground">
              No repositories match &ldquo;{search}&rdquo;
            </p>
            <Button variant="ghost" size="sm" onClick={() => setSearch("")}>
              Clear search
            </Button>
          </div>
        )}
      </div>

      {/* Delete dialog */}
      <DeleteRepositoryDialog
        repositoryName={deleteTarget?.name ?? ""}
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        onConfirm={handleDelete}
      />
    </AppShell>
  );
}
