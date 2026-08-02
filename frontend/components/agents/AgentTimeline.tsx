"use client";

import { cn } from "@/lib/utils";
import type { AgentState } from "@/lib/types";

interface AgentTimelineProps {
  agents: AgentState[];
}

/**
 * Compact timeline view showing the execution order and status of agents.
 * Uses a vertical timeline layout with connecting lines.
 */
export function AgentTimeline({ agents }: AgentTimelineProps) {
  if (agents.length === 0) {
    return (
      <p className="text-xs text-muted-foreground text-center py-4">
        暂无执行记录
      </p>
    );
  }

  return (
    <div className="space-y-0">
      {agents.map((agent, index) => {
        const isLast = index === agents.length - 1;
        const isActive = agent.status === "running";
        const isComplete = agent.status === "completed";

        return (
          <div key={agent.name} className="flex items-start gap-3">
            {/* Timeline line + dot */}
            <div className="flex flex-col items-center">
              <div
                className={cn(
                  "h-3 w-3 rounded-full border-2 shrink-0",
                  isActive && "border-agent-running bg-agent-running/30",
                  isComplete && "border-agent-completed bg-agent-completed",
                  !isActive && !isComplete && "border-muted bg-muted/30",
                )}
              />
              {!isLast && (
                <div
                  className={cn(
                    "w-0.5 h-6",
                    isComplete ? "bg-agent-completed/50" : "bg-border",
                  )}
                />
              )}
            </div>

            {/* Content */}
            <div className={cn("pb-2 -mt-0.5", !isActive && !isComplete && "opacity-50")}>
              <div className="flex items-center gap-1.5">
                <span className="text-xs">{agent.icon}</span>
                <span className="text-xs font-medium text-foreground">{agent.displayName}</span>
              </div>
              {agent.summary && (
                <p className="text-xs text-muted-foreground mt-0.5 truncate max-w-[200px]">
                  {agent.summary}
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
