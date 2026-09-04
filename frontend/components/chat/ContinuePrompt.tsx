"use client";

interface ContinuePromptProps {
  onContinue: (phase: string) => void;
  disabled?: boolean;
  recommendation?: string;
  hasPrd?: boolean;
}

/** Shown after decision completes — nudge user to the next phase. */
export function ContinuePrompt({
  onContinue,
  disabled,
  recommendation,
  hasPrd = false,
}: ContinuePromptProps) {
  const isKill = recommendation === "KILL";
  const isPivot = recommendation === "PIVOT";

  return (
    <div className="rounded-lg border border-border bg-secondary/50 px-4 py-3">
      <p className="text-sm text-foreground">
        {isKill ? "当前建议暂缓进入 PRD。" : "决策分析已完成。下一步？"}
      </p>
      <p className="mt-0.5 text-[11px] text-muted-foreground">
        {isKill
          ? "请在输入框补充新的证据或调整需求方向，再重新进行决策。"
          : isPivot
            ? "建议先确认调整方向；继续即表示接受当前 PIVOT 建议并生成 PRD。"
            : "继续后会生成 PRD，并自动完成质量审查和压力测试。"}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        {!isKill && (
          <button
            type="button"
            disabled={disabled}
            onClick={() => onContinue("prd_generation")}
            className="rounded-md bg-primary px-3 py-1.5 text-xs text-primary-foreground disabled:opacity-50"
          >
            {isPivot ? "按调整建议生成 PRD" : "继续生成 PRD"}
          </button>
        )}
        {hasPrd && (
          <button
            type="button"
            disabled={disabled}
            onClick={() => onContinue("stress_test")}
            className="rounded-md border border-border bg-background px-3 py-1.5 text-xs text-muted-foreground hover:bg-accent disabled:opacity-50"
          >
            仅压力测试
          </button>
        )}
      </div>
    </div>
  );
}
