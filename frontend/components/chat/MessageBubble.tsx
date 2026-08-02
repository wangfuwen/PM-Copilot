"use client";

import { cn } from "@/lib/utils";
import { ClarifyOptions, SKIP_CLARIFY_TOKEN } from "./ClarifyOptions";
import { MemoryCitationsBlock } from "./MemoryCitationsBlock";
import { ContinuePrompt } from "./ContinuePrompt";
import type { Message, ClarifyStep, MemoryCitation } from "@/lib/types";

interface MessageBubbleProps {
  message: Message;
  onClarifySelect?: (value: string) => void;
  onContinue?: (phase: string) => void;
  clarifyDisabled?: boolean;
}

const AGENT_INFO: Record<string, { name: string; icon: string }> = {
  orchestrator: { name: "编排器", icon: "🧭" },
  org_memory: { name: "组织记忆", icon: "🧠" },
  decision: { name: "决策顾问", icon: "🎯" },
  prd_writer: { name: "PRD 撰写", icon: "📝" },
  stress_test: { name: "压力测试", icon: "⚡" },
  memory_writeback: { name: "记忆回流", icon: "💾" },
  critic: { name: "质量审查", icon: "🔍" },
};

export function MessageBubble({
  message,
  onClarifySelect,
  onContinue,
  clarifyDisabled,
}: MessageBubbleProps) {
  const { role, content, agentName, timestamp, metadata } = message;
  const agentInfo = agentName ? AGENT_INFO[agentName] : null;
  const clarifyStep = (metadata?.clarify_step as ClarifyStep | undefined) || undefined;
  const clarifyAnswered = Boolean(metadata?.clarify_answered);
  const citations = (metadata?.citations as MemoryCitation[] | undefined) || undefined;
  const isCitationsMsg = metadata?.kind === "citations" || Boolean(citations?.length);
  const isContinueMsg = metadata?.kind === "continue_prompt";
  const isError = role === "system" && metadata?.kind !== "citations";

  const showClarify =
    Boolean(clarifyStep?.question) &&
    Boolean(onClarifySelect) &&
    !clarifyAnswered;

  // Dedicated layouts
  if (isCitationsMsg && citations) {
    return (
      <div className="flex gap-3 justify-start">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-secondary text-sm">
          🧠
        </div>
        <div className="max-w-[80%] min-w-[240px]">
          <MemoryCitationsBlock citations={citations} defaultCollapsed />
          <div className="mt-1 text-right text-xs text-muted-foreground opacity-50" suppressHydrationWarning>
            {timestamp.toLocaleTimeString("zh-CN", {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </div>
        </div>
      </div>
    );
  }

  if (isContinueMsg && onContinue) {
    return (
      <div className="flex gap-3 justify-start">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-secondary text-sm">
          ➡️
        </div>
        <div className="max-w-[80%] min-w-[280px]">
          <ContinuePrompt onContinue={onContinue} disabled={clarifyDisabled} />
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn("flex gap-3", {
        "justify-end": role === "user",
        "justify-start": role !== "user",
      })}
    >
      {role !== "user" && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-secondary text-sm">
          {agentInfo?.icon || "💬"}
        </div>
      )}

      <div
        className={cn("max-w-[80%] rounded-lg px-4 py-2.5", {
          "bg-primary text-primary-foreground": role === "user",
          "bg-secondary text-secondary-foreground": role === "assistant",
          "bg-destructive/20 text-destructive border border-destructive/30": isError,
        })}
      >
        {agentInfo && (
          <div className="mb-1 text-xs font-medium text-muted-foreground">
            {agentInfo.icon} {agentInfo.name}
          </div>
        )}

        <div className="whitespace-pre-wrap text-sm leading-relaxed markdown-content text-foreground">
          {renderContent(displayContent(content, clarifyStep))}
        </div>

        {showClarify && clarifyStep && (
          <ClarifyOptions
            step={clarifyStep}
            disabled={clarifyDisabled}
            onSelect={onClarifySelect!}
          />
        )}

        {clarifyAnswered && clarifyStep && (
          <p className="mt-2 text-[11px] text-muted-foreground">已回答</p>
        )}

        <div className="mt-1 text-right text-xs opacity-50" suppressHydrationWarning>
          {timestamp.toLocaleTimeString("zh-CN", {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </div>
      </div>

      {role === "user" && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">
          U
        </div>
      )}
    </div>
  );
}

function displayContent(content: string, step?: ClarifyStep): string {
  if (step?.question) {
    const hint = step.hint ? `\n\n_${step.hint}_` : "";
    return `${step.question}${hint}`;
  }
  if (content.includes("```json")) {
    return content.replace(/```json[\s\S]*?```/g, "").trim();
  }
  if (content === SKIP_CLARIFY_TOKEN) {
    return "跳过，直接决策";
  }
  return content;
}

function renderContent(content: string): React.ReactNode {
  const lines = content.split("\n");
  return lines.map((line, i) => {
    let processed = line.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    processed = processed.replace(/_(.*?)_/g, "<em>$1</em>");
    if (processed.startsWith("## ")) {
      return (
        <h2
          key={i}
          className="text-base font-semibold mt-3 mb-1 text-foreground"
          dangerouslySetInnerHTML={{ __html: processed.slice(3) }}
        />
      );
    }
    if (processed.startsWith("### ")) {
      return (
        <h3
          key={i}
          className="text-sm font-semibold mt-2 mb-1 text-foreground"
          dangerouslySetInnerHTML={{ __html: processed.slice(4) }}
        />
      );
    }
    if (processed.startsWith("- ")) {
      return (
        <li
          key={i}
          className="ml-4 list-disc text-foreground"
          dangerouslySetInnerHTML={{ __html: processed.slice(2) }}
        />
      );
    }
    if (processed.trim() === "") {
      return <br key={i} />;
    }
    return (
      <p
        key={i}
        className="mb-1 text-foreground"
        dangerouslySetInnerHTML={{ __html: processed }}
      />
    );
  });
}
