"use client";

import { useRef, useEffect } from "react";
import { MessageBubble } from "./MessageBubble";
import type { Message, IssueStatus } from "@/lib/types";

interface ChatWindowProps {
  messages: Message[];
  isLoading: boolean;
  onClarifySelect?: (value: string) => void;
  onContinue?: (phase: string) => void;
  onIssueStatusChange?: (
    messageId: string,
    issueIndex: number,
    status: IssueStatus,
  ) => void;
  onApplyAcceptedIssues?: (messageId: string) => void;
}

export function ChatWindow({
  messages,
  isLoading,
  onClarifySelect,
  onContinue,
  onIssueStatusChange,
  onApplyAcceptedIssues,
}: ChatWindowProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  // Scroll only the chat container — never the page (scrollIntoView can shift the whole UI).
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages, isLoading]);

  return (
    <div
      ref={scrollRef}
      className="min-h-0 flex-1 overflow-y-auto px-6 py-4"
    >
      <div className="mx-auto max-w-3xl space-y-4">
        {messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            message={msg}
            onClarifySelect={onClarifySelect}
            onContinue={onContinue}
            onIssueStatusChange={onIssueStatusChange}
            onApplyAcceptedIssues={onApplyAcceptedIssues}
            clarifyDisabled={isLoading}
          />
        ))}

        {isLoading && (
          <div className="flex items-center gap-2 px-4 py-2">
            <div className="flex gap-1">
              <span
                className="h-2 w-2 rounded-full bg-primary animate-pulse-dot"
                style={{ animationDelay: "0ms" }}
              />
              <span
                className="h-2 w-2 rounded-full bg-primary animate-pulse-dot"
                style={{ animationDelay: "300ms" }}
              />
              <span
                className="h-2 w-2 rounded-full bg-primary animate-pulse-dot"
                style={{ animationDelay: "600ms" }}
              />
            </div>
            <span className="text-xs text-muted-foreground">Agent 正在思考...</span>
          </div>
        )}
      </div>
    </div>
  );
}
