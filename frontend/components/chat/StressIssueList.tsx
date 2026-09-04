"use client";

import type {
  IssueStatus,
  StressTestChallenge,
  StressTestSummary,
} from "@/lib/types";

interface StressIssueListProps {
  challenges: StressTestChallenge[];
  summary?: StressTestSummary;
  disabled?: boolean;
  onStatusChange: (index: number, status: IssueStatus) => void;
  onApplyAccepted: () => void;
}

const SEVERITY_ORDER = { critical: 0, high: 1, medium: 2, low: 3 } as const;
const SEVERITY_LABEL = {
  critical: "致命",
  high: "重要",
  medium: "一般",
  low: "建议",
} as const;
const SEVERITY_STYLE = {
  critical: "border-red-500/50 bg-red-500/10 text-red-200",
  high: "border-orange-500/50 bg-orange-500/10 text-orange-200",
  medium: "border-amber-500/40 bg-amber-500/10 text-amber-100",
  low: "border-emerald-500/40 bg-emerald-500/10 text-emerald-100",
} as const;

export function StressIssueList({
  challenges,
  summary,
  disabled,
  onStatusChange,
  onApplyAccepted,
}: StressIssueListProps) {
  const items = challenges
    .map((issue, index) => ({ issue, index }))
    .sort(
      (a, b) =>
        SEVERITY_ORDER[a.issue.severity] - SEVERITY_ORDER[b.issue.severity],
    );
  const acceptedCount = challenges.filter(
    (issue) => issue.status === "accepted",
  ).length;
  const openCount = challenges.filter(
    (issue) => !issue.status || issue.status === "open",
  ).length;

  return (
    <div className="rounded-lg border border-border bg-secondary/50 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-foreground">压力测试问题清单</h3>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            共 {challenges.length} 项 · 待处理 {openCount} · 已接受 {acceptedCount}
          </p>
        </div>
        {summary?.overall_score !== null && summary?.overall_score !== undefined && (
          <div className="rounded border border-border bg-background px-2 py-1 text-xs text-foreground">
            {summary.overall_score}/100
          </div>
        )}
      </div>

      {(summary?.failed_roles?.length || 0) > 0 && (
        <p className="mt-2 text-[11px] text-amber-200">
          未完成角色：{summary!.failed_roles!.join("、")}。其他评审结果已正常保留。
        </p>
      )}

      <div className="mt-3 space-y-2">
        {items.map(({ issue, index }) => {
          const status = issue.status || "open";
          return (
            <div
              key={issue.id || `${issue.role}-${index}`}
              className={`rounded-md border p-3 ${
                status === "dismissed" ? "border-border opacity-55" : "border-border"
              }`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={`rounded border px-1.5 py-0.5 text-[10px] ${SEVERITY_STYLE[issue.severity]}`}
                >
                  {SEVERITY_LABEL[issue.severity]}
                </span>
                <span className="text-[11px] text-muted-foreground">{issue.role}</span>
                {status !== "open" && (
                  <span className="text-[10px] text-muted-foreground">
                    {status === "accepted"
                      ? "已接受"
                      : status === "applied"
                        ? "已应用"
                        : "已忽略"}
                  </span>
                )}
              </div>
              <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-foreground">
                {issue.challenge}
              </p>
              {issue.suggestions?.length > 0 && (
                <ul className="mt-2 list-disc space-y-0.5 pl-4 text-xs text-muted-foreground">
                  {issue.suggestions.map((suggestion, suggestionIndex) => (
                    <li key={suggestionIndex}>{suggestion}</li>
                  ))}
                </ul>
              )}
              {status !== "applied" && (
                <div className="mt-3 flex gap-2">
                  <button
                    type="button"
                    disabled={disabled}
                    onClick={() =>
                      onStatusChange(index, status === "accepted" ? "open" : "accepted")
                    }
                    className={`rounded px-2 py-1 text-[11px] disabled:opacity-40 ${
                      status === "accepted"
                        ? "bg-primary text-primary-foreground"
                        : "border border-border bg-background text-foreground"
                    }`}
                  >
                    {status === "accepted" ? "取消接受" : "接受建议"}
                  </button>
                  <button
                    type="button"
                    disabled={disabled}
                    onClick={() =>
                      onStatusChange(index, status === "dismissed" ? "open" : "dismissed")
                    }
                    className="rounded border border-border bg-background px-2 py-1 text-[11px] text-muted-foreground disabled:opacity-40"
                  >
                    {status === "dismissed" ? "恢复" : "忽略"}
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <button
        type="button"
        disabled={disabled || acceptedCount === 0}
        onClick={onApplyAccepted}
        className="mt-3 w-full rounded-md bg-primary px-3 py-2 text-xs font-medium text-primary-foreground disabled:cursor-not-allowed disabled:opacity-40"
      >
        应用已接受建议并生成新版本{acceptedCount > 0 ? `（${acceptedCount}）` : ""}
      </button>
    </div>
  );
}
