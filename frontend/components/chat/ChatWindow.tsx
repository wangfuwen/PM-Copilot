"use client";

import { useRef, useEffect } from "react";
import { MessageBubble } from "./MessageBubble";
import type { Message } from "@/lib/types";

interface ChatWindowProps {
  messages: Message[];
  isLoading: boolean;
}

/**
 * Chat window component that displays the conversation history.
 * Auto-scrolls to the bottom when new messages arrive.
 */
export function ChatWindow({ messages, isLoading }: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="flex-1 overflow-y-auto px-6 py-4">
      <div className="mx-auto max-w-3xl space-y-4">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}

        {/* Loading indicator */}
        {isLoading && (
          <div className="flex items-center gap-2 px-4 py-2">
            <div className="flex gap-1">
              <span className="h-2 w-2 rounded-full bg-primary animate-pulse-dot" style={{ animationDelay: "0ms" }} />
              <span className="h-2 w-2 rounded-full bg-primary animate-pulse-dot" style={{ animationDelay: "300ms" }} />
              <span className="h-2 w-2 rounded-full bg-primary animate-pulse-dot" style={{ animationDelay: "600ms" }} />
            </div>
            <span className="text-xs text-muted-foreground">Agent 正在思考...</span>
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}
