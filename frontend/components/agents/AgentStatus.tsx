"use client";

import { cn } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import type { AgentState, AgentStatus as AgentStatusType } from "@/lib/types";

interface AgentStatusProps {
  agents: AgentState[];
}

const STATUS_STYLES: Record<AgentStatusType, { dot: string; text: string; label: string }> = {
  pending: {
    dot: "bg-agent-pending",
    text: "text-agent-pending",
    label: "等待中",
  },
  running: {
    dot: "bg-agent-running animate-pulse-dot",
    text: "text-agent-running",
    label: "执行中",
  },
  completed: {
    dot: "bg-agent-completed",
    text: "text-agent-completed",
    label: "已完成",
  },
  failed: {
    dot: "bg-agent-failed",
    text: "text-agent-failed",
    label: "失败",
  },
  skipped: {
    dot: "bg-agent-pending opacity-50",
    text: "text-agent-pending opacity-50",
    label: "已跳过",
  },
};

/**
 * Agent status panel showing the current state of each agent.
 * Displays status dots, names, and timing information.
 */
export function AgentStatus({ agents }: AgentStatusProps) {
  if (agents.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <span className="text-3xl mb-3">🤖</span>
        <p className="text-sm text-muted-foreground">
          发送消息开始 Multi-Agent 协作
        </p>
        <p className="text-xs text-muted-foreground mt-1">
          Agent 状态将在这里实时展示
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {agents.map((agent) => {
        const style = STATUS_STYLES[agent.status];
        return (
          <Card key={agent.name} className="p-3 transition-agent">
            <div className="flex items-center gap-3">
              {/* Status dot */}
              <span className={cn("h-2.5 w-2.5 rounded-full shrink-0", style.dot)} />

              {/* Icon */}
              <span className="text-lg">{agent.icon}</span>

              {/* Name and status */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-foreground truncate">
                    {agent.displayName}
                  </span>
                  <span className={cn("text-xs", style.text)}>{style.label}</span>
                </div>

                {/* Timing info */}
                {agent.startedAt && (
                  <div className="text-xs text-muted-foreground mt-0.5">
                    {new Date(agent.startedAt).toLocaleTimeString("zh-CN", {
                      hour: "2-digit",
                      minute: "2-digit",
                      second: "2-digit",
                    })}
                    {agent.completedAt && (
                      <> → {new Date(agent.completedAt).toLocaleTimeString("zh-CN", {
                        hour: "2-digit",
                        minute: "2-digit",
                        second: "2-digit",
                      })}</>
                    )}
                  </div>
                )}
              </div>
            </div>
          </Card>
        );
      })}
    </div>
  );
}
