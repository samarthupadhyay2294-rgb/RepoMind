"use client";

import { useState, useRef, useEffect } from "react";
import { Loader2, SendHorizonal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

const MAX_LENGTH = 4000;

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  loading?: boolean;
}

export function ChatInput({ onSend, disabled, loading }: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const trimmed = value.trim();
  const canSend = trimmed.length > 0 && trimmed.length <= MAX_LENGTH && !disabled && !loading;

  useEffect(() => {
    if (!loading && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [loading]);

  function handleSend() {
    if (!canSend) return;
    onSend(trimmed);
    setValue("");
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="relative">
      <Textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask about this repository..."
        disabled={disabled || loading}
        rows={2}
        maxLength={MAX_LENGTH + 100}
        className="min-h-[60px] resize-none pr-14"
      />
      <div className="absolute bottom-2 right-2 flex items-center gap-2">
        <span className="text-xs text-muted-foreground tabular-nums">
          {value.length > 0 ? `${value.length}/${MAX_LENGTH}` : ""}
        </span>
        <Button
          size="icon"
          className="h-8 w-8"
          disabled={!canSend}
          onClick={handleSend}
          aria-label="Send message"
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <SendHorizonal className="h-4 w-4" />
          )}
        </Button>
      </div>
    </div>
  );
}
