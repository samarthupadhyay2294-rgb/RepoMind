"use client";

import { useState } from "react";
import { FolderGit2, GitBranch, Loader2, Plus, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { RepositoryCreate, SourceType } from "@/lib/types";
import { ApiError } from "@/lib/api";

interface AddRepositoryDialogProps {
  onAdd: (data: RepositoryCreate) => Promise<void>;
}

export function AddRepositoryDialog({ onAdd }: AddRepositoryDialogProps) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sourceType, setSourceType] = useState<SourceType>("git");
  const [name, setName] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [localPath, setLocalPath] = useState("");
  const [defaultBranch, setDefaultBranch] = useState("");

  function reset() {
    setName("");
    setSourceUrl("");
    setLocalPath("");
    setDefaultBranch("");
    setError(null);
    setSourceType("git");
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (!name.trim()) {
      setError("Repository name is required.");
      return;
    }

    if (sourceType === "git" && !sourceUrl.trim()) {
      setError("Repository URL is required for git repositories.");
      return;
    }

    if (sourceType === "local" && !localPath.trim()) {
      setError("Local path is required for local repositories.");
      return;
    }

    setLoading(true);
    try {
      await onAdd({
        name: name.trim(),
        source_type: sourceType,
        ...(sourceType === "git" ? { source_url: sourceUrl.trim() } : {}),
        ...(sourceType === "local" ? { local_path: localPath.trim() } : {}),
        ...(defaultBranch.trim() ? { default_branch: defaultBranch.trim() } : {}),
      });
      setOpen(false);
      reset();
    } catch (err: unknown) {
      let message = "Failed to add repository.";
      if (err instanceof ApiError) {
        if (err.code === "BACKEND_UNREACHABLE") {
          message = "Unable to connect to the backend server. Please check if the server is running.";
        } else if (err.code === "REQUEST_TIMEOUT") {
          message = "Request timed out while adding repository.";
        } else if (err.status === 422) {
          message = "Invalid repository data. Please check your input and try again.";
        } else if (err.status === 500) {
          message = "Server error occurred. Please try again later.";
        } else {
          message = err.message;
        }
      } else if (err instanceof Error) {
        message = err.message;
      }
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (!v) reset();
      }}
    >
      <DialogTrigger render={<Button className="w-full sm:w-auto shrink-0 whitespace-nowrap gap-2" />}>
        <Plus className="h-4 w-4 shrink-0" />
        <span>Add Repository</span>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Add Repository</DialogTitle>
            <DialogDescription>
              Connect a repository to start exploring your codebase with RepoMind.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <Tabs
              value={sourceType}
              onValueChange={(v: string) => setSourceType(v as SourceType)}
            >
              <TabsList className="w-full">
                <TabsTrigger value="git" className="flex-1">
                  <GitBranch className="mr-2 h-4 w-4" />
                  Git URL
                </TabsTrigger>
                <TabsTrigger value="local" className="flex-1">
                  <FolderGit2 className="mr-2 h-4 w-4" />
                  Local Path
                </TabsTrigger>
              </TabsList>

              <TabsContent value="git" className="space-y-4 pt-2">
                <div className="space-y-2">
                  <Label htmlFor="repo-url">Repository URL</Label>
                  <Input
                    id="repo-url"
                    placeholder="https://github.com/user/project"
                    value={sourceUrl}
                    onChange={(e) => setSourceUrl(e.target.value)}
                    disabled={loading}
                  />
                </div>
              </TabsContent>

              <TabsContent value="local" className="space-y-4 pt-2">
                <div className="space-y-2">
                  <Label htmlFor="local-path">Local Path</Label>
                  <Input
                    id="local-path"
                    placeholder="/path/to/repository"
                    value={localPath}
                    onChange={(e) => setLocalPath(e.target.value)}
                    disabled={loading}
                  />
                </div>
              </TabsContent>
            </Tabs>

            <div className="space-y-2">
              <Label htmlFor="repo-name">Repository Name</Label>
              <Input
                id="repo-name"
                placeholder="My Project"
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={loading}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="branch">Default Branch (optional)</Label>
              <Input
                id="branch"
                placeholder="main"
                value={defaultBranch}
                onChange={(e) => setDefaultBranch(e.target.value)}
                disabled={loading}
              />
            </div>

            {error && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
              disabled={loading}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={loading}>
              {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Add Repository
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
