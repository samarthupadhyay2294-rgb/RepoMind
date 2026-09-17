"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { AppShell } from "@/components/layout/app-shell";
import { ChatMessage } from "@/components/chat/chat-message";
import { ChatInput } from "@/components/chat/chat-input";
import { CitationCard } from "@/components/chat/citation-card";
import { ChatLoadingSkeleton } from "@/components/chat/chat-loading";
import { ChatError } from "@/components/chat/chat-error";
import { EmptyChatState, InsufficientEvidenceState } from "@/components/chat/empty-states";
import { sendChatMessage, getRepository } from "@/lib/api";
import type {
  ChatCitation,
  ChatResponse,
  Repository,
} from "@/lib/types";
import Link from "next/link";

interface DisplayMessage {
  role: "user" | "assistant";
  content?: string;
  citations?: ChatCitation[];
  warnings?: string[];
  requestType?: string;
  loading?: boolean;
}

export default function RepositoryChatPage() {
  const params = useParams();
  const id = params.id as string;

  const [repo, setRepo] = useState<Repository | null>(null);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | undefined>(undefined);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getRepository(id).then(setRepo).catch(() => {});
  }, [id]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = useCallback(
    async (question: string) => {
      setError(null);
      setMessages((prev) => [
        ...prev,
        { role: "user", content: question },
        { role: "assistant", loading: true },
      ]);
      setLoading(true);

      try {
        const res: ChatResponse = await sendChatMessage({
          repository_id: id,
          question,
          session_id: sessionId,
        });

        if (!sessionId) setSessionId(res.session_id);

        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            role: "assistant",
            content: res.answer,
            citations: res.citations,
            warnings: res.warnings,
            requestType: res.request_type,
          };
          return updated;
        });
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Failed to send message.";
        setError(msg);
        setMessages((prev) => prev.slice(0, -1));
      } finally {
        setLoading(false);
      }
    },
    [id, sessionId],
  );

  return (
    <AppShell>
      <div className="flex h-full flex-col">
        {/* Header */}
        <div className="flex items-center gap-3 border-b px-4 h-14 shrink-0">
          <Link
            href={`/repositories/${id}`}
            aria-label="Back to repository"
            className={buttonVariants({ variant: "ghost", size: "icon", className: "h-8 w-8" })}
          >
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <Separator orientation="vertical" className="h-6" />
          <div className="min-w-0">
            <p className="text-sm font-medium truncate">{repo?.name ?? "Repository"}</p>
            <p className="text-xs text-muted-foreground">Chat</p>
          </div>
        </div>

        {/* Messages */}
        <ScrollArea className="flex-1" ref={scrollRef}>
          <div className="mx-auto max-w-3xl space-y-4 p-4">
            {messages.length === 0 && !loading && <EmptyChatState />}

            {messages.map((msg, i) => (
              <div key={i} className="space-y-3">
                {msg.loading ? (
                  <ChatLoadingSkeleton />
                ) : (
                  <ChatMessage role={msg.role}>
                    {msg.role === "assistant" && msg.warnings && msg.warnings.length > 0 && (
                      <div className="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground space-y-1 mb-2">
                        {msg.warnings.map((w, j) => (
                          <p key={j}>{w}</p>
                        ))}
                      </div>
                    )}
                    {msg.content ? (
                      <div className="prose prose-sm dark:prose-invert max-w-none">
                        <p className="whitespace-pre-wrap">{msg.content}</p>
                      </div>
                    ) : (
                      <InsufficientEvidenceState />
                    )}
                    {msg.citations && msg.citations.length > 0 && (
                      <div className="mt-3 space-y-2">
                        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                          Sources
                        </p>
                        <div className="grid gap-2 sm:grid-cols-2">
                          {msg.citations.map((c, j) => (
                            <CitationCard key={j} citation={c} />
                          ))}
                        </div>
                      </div>
                    )}
                  </ChatMessage>
                )}
              </div>
            ))}

            {error && (
              <ChatError
                message={error}
                onRetry={() => {
                  const lastUser = [...messages].reverse().find((m) => m.role === "user");
                  if (lastUser?.content) {
                    setError(null);
                    handleSend(lastUser.content);
                  }
                }}
              />
            )}
          </div>
        </ScrollArea>

        {/* Input */}
        <div className="border-t p-4 shrink-0">
          <div className="mx-auto max-w-3xl">
            <ChatInput onSend={handleSend} loading={loading} />
          </div>
        </div>
      </div>
    </AppShell>
  );
}
