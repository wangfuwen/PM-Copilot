"use client";

import { cn } from "@/lib/utils";
import type { ClarifyOption, ClarifyStep } from "@/lib/types";

export const SKIP_CLARIFY_TOKEN = "__SKIP_CLARIFY__";

interface ClarifyOptionsProps {
  step: ClarifyStep;
  disabled?: boolean;
  onSelect: (value: string) => void;
}

/**
 * Cursor-style single-step clarify chips: pick an option, skip, or type below.
 */
export function ClarifyOptions({ step, disabled, onSelect }: ClarifyOptionsProps) {
  const options = step.options || [];
  const progress =
    step.step && step.max_steps ? `${step.step}/${step.max_steps}` : null;

  return (
    <div className="mt-3 space-y-2">
      {progress && (
        <p className="text-[11px] text-muted-foreground">确认 {progress}</p>
      )}
      <div className="flex flex-wrap gap-2">
        {options.map((opt: ClarifyOption) => (
          <button
            key={opt.id}
            type="button"
            disabled={disabled}
            onClick={() => onSelect(opt.label)}
            className={cn(
              "rounded-md border border-border bg-background px-3 py-1.5 text-left text-xs",
              "text-foreground transition-colors hover:border-ring hover:bg-accent",
              "disabled:cursor-not-allowed disabled:opacity-40",
            )}
          >
            {opt.label}
          </button>
        ))}
        <button
          type="button"
          disabled={disabled}
          onClick={() => onSelect(SKIP_CLARIFY_TOKEN)}
          className={cn(
            "rounded-md border border-dashed border-border px-3 py-1.5 text-xs",
            "text-muted-foreground transition-colors hover:border-ring hover:text-foreground",
            "disabled:cursor-not-allowed disabled:opacity-40",
          )}
        >
          跳过，直接决策
        </button>
      </div>
      {step.allow_custom !== false && (
        <p className="text-[11px] text-muted-foreground">
          也可以在下方输入框自己补充一句
        </p>
      )}
    </div>
  );
}
