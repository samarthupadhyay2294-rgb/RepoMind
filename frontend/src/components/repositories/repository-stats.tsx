"use client";

import { useEffect, useState } from "react";
import { FileCode2, GitCommitHorizontal, Layers, Clock } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";

interface StatCardProps {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string | number;
}

function StatCard({ icon: Icon, label, value }: StatCardProps) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 p-4">
        <div className="rounded-md bg-muted p-2">
          <Icon className="h-4 w-4 text-muted-foreground" />
        </div>
        <div>
          <p className="text-2xl font-semibold leading-none">{value}</p>
          <p className="text-xs text-muted-foreground mt-1">{label}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function formatTimeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  if (diff < 60_000) return "just now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return `${Math.floor(diff / 86_400_000)}d ago`;
}

interface RepositoryStatsProps {
  fileCount?: number;
  chunkCount?: number;
  commitSha?: string | null;
  updatedAt?: string;
}

export function RepositoryStats({
  fileCount,
  chunkCount,
  commitSha,
  updatedAt,
}: RepositoryStatsProps) {
  const [timeLabel, setTimeLabel] = useState(() =>
    updatedAt ? formatTimeAgo(updatedAt) : "",
  );

  useEffect(() => {
    if (!updatedAt) return;
    const interval = setInterval(() => {
      setTimeLabel(formatTimeAgo(updatedAt));
    }, 60_000);
    return () => clearInterval(interval);
  }, [updatedAt]);

  const stats: StatCardProps[] = [];

  if (fileCount !== undefined) {
    stats.push({ icon: FileCode2, label: "Files", value: fileCount.toLocaleString() });
  }
  if (chunkCount !== undefined) {
    stats.push({ icon: Layers, label: "Chunks", value: chunkCount.toLocaleString() });
  }
  if (commitSha) {
    stats.push({
      icon: GitCommitHorizontal,
      label: "Commit",
      value: commitSha.slice(0, 7),
    });
  }
  if (updatedAt) {
    stats.push({ icon: Clock, label: "Last indexed", value: timeLabel });
  }

  if (stats.length === 0) return null;

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {stats.map((s) => (
        <StatCard key={s.label} {...s} />
      ))}
    </div>
  );
}
