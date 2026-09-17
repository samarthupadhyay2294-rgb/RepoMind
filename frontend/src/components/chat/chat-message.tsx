"use client";

import { cn } from "@/lib/utils";
import { User, Bot } from "lucide-react";

interface ChatMessageProps {
  role: "user" | "assistant";
  children: React.ReactNode;
}

export function ChatMessage({ role, children }: ChatMessageProps) {
  const isUser = role === "user";

  return (
    <div
      className={cn(
        "flex gap-3 rounded-lg px-4 py-3",
        isUser ? "bg-muted" : "bg-card border",
      )}
    >
      <div
        className={cn(
          "flex h-7 w-7 shrink-0 items-center justify-center rounded-full",
          isUser ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground",
        )}
      >
        {isUser ? <User className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5" />}
      </div>
      <div className="min-w-0 flex-1 space-y-2 text-sm leading-relaxed">
        {children}
      </div>
    </div>
  );
}
