import { FileCode2 } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { ChatCitation } from "@/lib/types";

interface CitationCardProps {
  citation: ChatCitation;
}

export function CitationCard({ citation }: CitationCardProps) {
  return (
    <Card className="py-2">
      <CardContent className="flex items-center justify-between gap-3 px-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <FileCode2 className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            <span className="text-sm font-mono truncate">{citation.file_path}</span>
          </div>
          <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
            <span>
              Lines {citation.start_line}–{citation.end_line}
            </span>
            {citation.source_type && (
              <>
                <span>·</span>
                <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                  {citation.source_type}
                </Badge>
              </>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
