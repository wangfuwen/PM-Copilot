"use client";

import { cn } from "@/lib/utils";
import type { Message, AgentName } from "@/lib/types";

interface MessageBubbleProps {
  message: Message;
}

// Agent display names and icons
const AGENT_INFO: Record<string, { name: string; icon: string }> = {
  orchestrator: { name: "编排器", icon: "🧭" },
  org_memory: { name: "组织记忆", icon: "🧠" },
  decision: { name: "决策顾问", icon: "🎯" },
  prd_writer: { name: "PRD 撰写", icon: "📝" },
  stress_test: { name: "压力测试", icon: "⚡" },
  memory_writeback: { name: "记忆回流", icon: "💾" },
  critic: { name: "质量审查", icon: "🔍" },
};

/**
 * Message bubble component with agent attribution.
 * Supports user, assistant, and system message styles.
 */
export function MessageBubble({ message }: MessageBubbleProps) {
  const { role, content, agentName, timestamp } = message;
  const agentInfo = agentName ? AGENT_INFO[agentName] : null;

  return (
    <div
      className={cn("flex gap-3", {
        "justify-end": role === "user",
        "justify-start": role !== "user",
      })}
    >
      {/* Agent icon (for assistant messages) */}
      {role !== "user" && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-secondary text-sm">
          {agentInfo?.icon || "💬"}
        </div>
      )}

      {/* Message content */}
      <div
        className={cn("max-w-[80%] rounded-lg px-4 py-2.5", {
          "bg-primary text-primary-foreground": role === "user",
          "bg-secondary text-secondary-foreground": role === "assistant",
          "bg-destructive/20 text-destructive border border-destructive/30": role === "system",
        })}
      >
        {/* Agent label */}
        {agentInfo && (
          <div className="mb-1 text-xs font-medium opacity-70">
            {agentInfo.icon} {agentInfo.name}
          </div>
        )}

        {/* Message text with basic markdown rendering */}
        <div className="whitespace-pre-wrap text-sm leading-relaxed markdown-content">
          {renderContent(content)}
        </div>

        {/* Timestamp */}
        <div className="mt-1 text-right text-xs opacity-50" suppressHydrationWarning>
          {timestamp.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}
        </div>
      </div>

      {/* User avatar */}
      {role === "user" && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">
          U
        </div>
      )}
    </div>
  );
}

/**
 * Simple content renderer with bold and list support.
 * For a production app, consider using react-markdown.
 */
function renderContent(content: string): React.ReactNode {
  // Split by double newlines for paragraphs
  const lines = content.split("\n");
  return lines.map((line, i) => {
    // Bold text
    let processed = line.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    // Headers
    if (processed.startsWith("## ")) {
      return <h2 key={i} className="text-lg font-bold mt-3 mb-1" dangerouslySetInnerHTML={{ __html: processed.slice(3) }} />;
    }
    if (processed.startsWith("### ")) {
      return <h3 key={i} className="text-base font-semibold mt-2 mb-1" dangerouslySetInnerHTML={{ __html: processed.slice(4) }} />;
    }
    // List items
    if (processed.startsWith("- ")) {
      return <li key={i} className="ml-4 list-disc" dangerouslySetInnerHTML={{ __html: processed.slice(2) }} />;
    }
    // Empty line
    if (processed.trim() === "") {
      return <br key={i} />;
    }
    // Regular text
    return <p key={i} className="mb-1" dangerouslySetInnerHTML={{ __html: processed }} />;
  });
}
