"use client";

interface ContinuePromptProps {
  onContinue: (phase: string) => void;
  disabled?: boolean;
}

/** Shown after decision completes — nudge user to the next phase. */
export function ContinuePrompt({ onContinue, disabled }: ContinuePromptProps) {
  return (
    <div className="rounded-lg border border-border bg-secondary/50 px-4 py-3">
      <p className="text-sm text-foreground">决策分析已完成。下一步？</p>
      <p className="mt-0.5 text-[11px] text-muted-foreground">
        可继续生成 PRD（随后会自动做质量审查；演示模式下压力测试可能跳过）。
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={disabled}
          onClick={() => onContinue("prd_generation")}
          className="rounded-md bg-primary px-3 py-1.5 text-xs text-primary-foreground disabled:opacity-50"
        >
          继续生成 PRD
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() => onContinue("stress_test")}
          className="rounded-md border border-border bg-background px-3 py-1.5 text-xs text-muted-foreground hover:bg-accent disabled:opacity-50"
        >
          仅压力测试
        </button>
      </div>
    </div>
  );
}
