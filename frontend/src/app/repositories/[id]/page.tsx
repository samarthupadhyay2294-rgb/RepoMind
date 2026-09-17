"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Bug,
  ExternalLink,
  Loader2,
  Map,
  MessageSquare,
  RefreshCw,
  Trash2,
  Workflow,
} from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { AppShell } from "@/components/layout/app-shell";
import { RepositoryStatusBadge } from "@/components/repositories/repository-status-badge";
import { RepositoryStats } from "@/components/repositories/repository-stats";
import { IndexingUI } from "@/components/repositories/indexing-ui";
import { DeleteRepositoryDialog } from "@/components/repositories/delete-repository-dialog";
import { getRepository, deleteRepository, startIndexing, getConfigDiagnostics } from "@/lib/api";
import type { Repository } from "@/lib/types";
import Link from "next/link";

export default function RepositoryDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [repo, setRepo] = useState<Repository | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [providerConfigured, setProviderConfigured] = useState<boolean | null>(
    null,
  );

  const fetchDiagnostics = useCallback(async () => {
    try {
      const d = await getConfigDiagnostics();
      setProviderConfigured(d.embedding_provider_configured);
    } catch {
      setProviderConfigured(null);
    }
  }, []);

  const fetchRepo = useCallback(async () => {
    try {
      const r = await getRepository(id);
      setRepo(r);
      setError(null);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load repository.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [r] = await Promise.all([
          getRepository(id),
          fetchDiagnostics(),
        ]);
        if (!cancelled) {
          setRepo(r);
          setError(null);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          const msg = err instanceof Error ? err.message : "Failed to load repository.";
          setError(msg);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [id, fetchRepo, fetchDiagnostics]);

  // Poll while indexing
  useEffect(() => {
    if (!repo || repo.status !== "indexing") return;
    const interval = setInterval(fetchRepo, 3000);
    return () => clearInterval(interval);
  }, [repo, fetchRepo]);

  async function handleDelete() {
    await deleteRepository(id);
    router.push("/");
  }

  const [indexing, setIndexing] = useState(false);

  async function handleStartIndexing() {
    setIndexing(true);
    try {
      const r = await startIndexing(id);
      setRepo(r);
      setError(null);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to start indexing.";
      setError(msg);
    } finally {
      setIndexing(false);
      fetchRepo();
      fetchDiagnostics();
    }
  }

  if (loading) {
    return (
      <AppShell>
        <div className="flex items-center justify-center py-24">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      </AppShell>
    );
  }

  if (error || !repo) {
    return (
      <AppShell>
        <div className="mx-auto max-w-3xl p-6 space-y-4">
          <Link href="/" className={buttonVariants({ variant: "ghost", size: "sm" })}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Repositories
          </Link>
          <div className="text-center py-12">
            <p className="text-muted-foreground">{error ?? "Repository not found."}</p>
            <Button variant="outline" size="sm" onClick={fetchRepo} className="mt-4">
              Retry
            </Button>
          </div>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="mx-auto max-w-3xl p-6 space-y-6">
        {/* Breadcrumb */}
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Link href="/" className="hover:text-foreground transition-colors">
            Repositories
          </Link>
          <span>/</span>
          <span className="text-foreground font-medium">{repo.name}</span>
        </div>

        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <h1 className="text-2xl font-bold tracking-tight">{repo.name}</h1>
            {repo.source_url && (
              <a
                href={repo.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-muted-foreground hover:text-foreground transition-colors inline-flex items-center gap-1"
              >
                {repo.source_url.replace(/^https?:\/\//, "")}
                <ExternalLink className="h-3 w-3" />
              </a>
            )}
            {repo.local_path && (
              <p className="text-sm text-muted-foreground font-mono">{repo.local_path}</p>
            )}
          </div>
          <RepositoryStatusBadge status={repo.status} />
        </div>

        {/* Stats */}
        <RepositoryStats
          commitSha={repo.current_commit_sha}
          updatedAt={repo.updated_at}
        />

        {/* Indexing */}
        <IndexingUI
          status={indexing ? "indexing" : repo.status}
          errorMessage={repo.error_message}
          onRetry={handleStartIndexing}
          providerConfigured={providerConfigured}
          retryBusy={indexing}
        />

        <Separator />

        {/* Actions */}
        <div className="flex items-center gap-3 flex-wrap">
          <Link href={`/repositories/${repo.id}/chat`} className={buttonVariants()}>
            <MessageSquare className="mr-2 h-4 w-4" />
            Chat
          </Link>
          <Link href={`/repositories/${repo.id}/overview`} className={buttonVariants({ variant: "outline" })}>
            <Map className="mr-2 h-4 w-4" />
            Overview
          </Link>
          <Link href={`/repositories/${repo.id}/graph`} className={buttonVariants({ variant: "outline" })}>
            <Workflow className="mr-2 h-4 w-4" />
            Graph
          </Link>
          <Link href={`/repositories/${repo.id}/debug`} className={buttonVariants({ variant: "outline" })}>
            <Bug className="mr-2 h-4 w-4" />
            Debug
          </Link>
          <Button variant="outline" onClick={fetchRepo}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh
          </Button>
          <div className="flex-1" />
          <Button variant="outline" onClick={() => setDeleteOpen(true)}>
            <Trash2 className="mr-2 h-4 w-4" />
            Delete
          </Button>
        </div>
      </div>

      <DeleteRepositoryDialog
        repositoryName={repo.name}
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        onConfirm={handleDelete}
      />
    </AppShell>
  );
}
