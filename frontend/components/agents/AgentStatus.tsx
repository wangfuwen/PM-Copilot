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
    label: "本轮未执行",
  },
};

function formatDuration(ms?: number): string {
  if (ms == null || Number.isNaN(ms)) return "—";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/**
 * Agent execution trajectory: status, duration, tokens, retries.
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
          将展示耗时、Token 与重试轨迹
        </p>
      </div>
    );
  }

  const totals = agents.reduce(
    (acc, a) => {
      acc.duration += a.durationMs || a.metrics?.duration_ms || 0;
      acc.tokens += a.tokens?.total || a.metrics?.tokens?.total || 0;
      acc.retries += a.retryCount || a.metrics?.retry_count || 0;
      return acc;
    },
    { duration: 0, tokens: 0, retries: 0 },
  );

  return (
    <div className="space-y-2">
      <div className="mb-2 flex flex-wrap gap-2 text-[10px] text-muted-foreground">
        <span className="rounded border border-border/60 px-1.5 py-0.5">
          总耗时 {formatDuration(totals.duration)}
        </span>
        <span className="rounded border border-border/60 px-1.5 py-0.5">
          Token {totals.tokens || "—"}
        </span>
        <span className="rounded border border-border/60 px-1.5 py-0.5">
          重试 {totals.retries}
        </span>
      </div>

      {agents.map((agent) => {
        const style = STATUS_STYLES[agent.status];
        const duration = agent.durationMs ?? agent.metrics?.duration_ms;
        const tokens = agent.tokens?.total ?? agent.metrics?.tokens?.total;
        const prompt = agent.tokens?.prompt ?? agent.metrics?.tokens?.prompt;
        const completion =
          agent.tokens?.completion ?? agent.metrics?.tokens?.completion;
        const retries = agent.retryCount ?? agent.metrics?.retry_count ?? 0;
        const error = agent.metrics?.error;

        return (
          <Card key={agent.name} className="p-3 transition-agent">
            <div className="flex items-start gap-3">
              <span
                className={cn("mt-1.5 h-2.5 w-2.5 rounded-full shrink-0", style.dot)}
              />
              <span className="text-lg leading-none">{agent.icon}</span>

              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium text-foreground">
                    {agent.displayName}
                  </span>
                  <span className={cn("shrink-0 text-xs", style.text)}>
                    {style.label}
                  </span>
                </div>

                {(agent.status === "completed" ||
                  agent.status === "failed" ||
                  agent.status === "running") && (
                  <div className="mt-1.5 grid grid-cols-3 gap-1 text-[10px] text-muted-foreground">
                    <div>
                      <div className="opacity-70">耗时</div>
                      <div className="font-medium text-foreground/80">
                        {agent.status === "running"
                          ? "…"
                          : formatDuration(duration)}
                      </div>
                    </div>
                    <div>
                      <div className="opacity-70">Token</div>
                      <div className="font-medium text-foreground/80">
                        {tokens != null && tokens > 0 ? tokens : "—"}
                      </div>
                    </div>
                    <div>
                      <div className="opacity-70">重试</div>
                      <div
                        className={cn(
                          "font-medium",
                          retries > 0 ? "text-amber-400" : "text-foreground/80",
                        )}
                      >
                        {retries}
                      </div>
                    </div>
                  </div>
                )}

                {(prompt || completion) && (
                  <div className="mt-1 text-[10px] text-muted-foreground">
                    in {prompt ?? 0} · out {completion ?? 0}
                  </div>
                )}

                {error && (
                  <div className="mt-1 line-clamp-2 text-[10px] text-red-400">
                    {error}
                  </div>
                )}

                {agent.summary && agent.status === "completed" && (
                  <p className="mt-1 truncate text-[10px] text-muted-foreground">
                    {agent.summary}
                  </p>
                )}
              </div>
            </div>
          </Card>
        );
      })}
    </div>
  );
}
