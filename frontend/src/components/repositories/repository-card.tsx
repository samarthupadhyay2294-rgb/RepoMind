import Link from "next/link";
import { ExternalLink, MessageSquare, MoreHorizontal, RefreshCw, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { RepositoryStatusBadge } from "./repository-status-badge";
import type { Repository } from "@/lib/types";

function timeAgo(date: string): string {
  const seconds = Math.floor(
    (Date.now() - new Date(date).getTime()) / 1000,
  );
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

interface RepositoryCardProps {
  repository: Repository;
  onDelete: (id: string) => void;
  onReindex: (id: string) => void;
}

export function RepositoryCard({
  repository,
  onDelete,
  onReindex,
}: RepositoryCardProps) {
  return (
    <Card className="group relative transition-shadow hover:shadow-md">
      <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-2">
        <CardTitle className="text-base font-semibold leading-none">
          <Link
            href={`/repositories/${repository.id}`}
            className="hover:underline"
          >
            {repository.name}
          </Link>
        </CardTitle>
        <DropdownMenu>
          <DropdownMenuTrigger render={<Button variant="ghost" size="icon" className="h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity" />}>
            <MoreHorizontal className="h-4 w-4" />
            <span className="sr-only">Actions</span>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => onReindex(repository.id)}>
              <RefreshCw className="mr-2 h-4 w-4" />
              Re-index
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => onDelete(repository.id)}
              className="text-destructive"
            >
              <Trash2 className="mr-2 h-4 w-4" />
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </CardHeader>
      <CardContent>
        <div className="flex items-center gap-2 text-sm text-muted-foreground mb-3">
          {repository.source_url && (
            <span className="truncate max-w-[200px]">
              {repository.source_url.replace(/^https?:\/\//, "")}
            </span>
          )}
          {repository.local_path && (
            <span className="truncate max-w-[200px]">{repository.local_path}</span>
          )}
        </div>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <RepositoryStatusBadge status={repository.status} />
            {repository.current_commit_sha && (
              <span className="text-xs text-muted-foreground font-mono">
                {repository.current_commit_sha.slice(0, 7)}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            <Tooltip>
              <TooltipTrigger
                render={
                  <Link href={`/repositories/${repository.id}`} className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-accent-foreground">
                    <ExternalLink className="h-4 w-4" />
                    <span className="sr-only">Open</span>
                  </Link>
                }
              />
              <TooltipContent>Open</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger
                render={
                  <Link href={`/repositories/${repository.id}/chat`} className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-accent-foreground">
                    <MessageSquare className="h-4 w-4" />
                    <span className="sr-only">Chat</span>
                  </Link>
                }
              />
              <TooltipContent>Chat</TooltipContent>
            </Tooltip>
          </div>
        </div>
        <p className="text-xs text-muted-foreground mt-2">
          Updated {timeAgo(repository.updated_at)}
        </p>
      </CardContent>
    </Card>
  );
}
