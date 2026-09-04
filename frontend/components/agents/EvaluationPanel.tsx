"use client";

import { cn } from "@/lib/utils";
import type { EvaluationResult } from "@/lib/types";

interface EvaluationPanelProps {
  evaluation: EvaluationResult | null;
}

const DIM_LABELS: Record<string, string> = {
  completeness: "完整性",
  consistency: "一致性",
  requirement_fit: "需求契合",
  clarity: "清晰度",
  actionability: "可落地性",
};

const VERDICT_STYLE: Record<string, string> = {
  STRONG: "text-emerald-400 border-emerald-500/40 bg-emerald-500/10",
  ADEQUATE: "text-sky-300 border-sky-500/40 bg-sky-500/10",
  WEAK: "text-amber-300 border-amber-500/40 bg-amber-500/10",
};

export function EvaluationPanel({ evaluation }: EvaluationPanelProps) {
  if (!evaluation) {
    return (
      <div className="rounded border border-border/60 px-3 py-4 text-center text-[11px] text-muted-foreground">
        决策或 PRD 完成后将显示自动评分
      </div>
    );
  }

  const scores = evaluation.scores || {};
  const target = evaluation.target === "prd" ? "PRD" : "决策";
  const verdict = evaluation.verdict || "—";

  return (
    <div className="space-y-2 text-xs">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h3 className="text-xs font-semibold text-foreground">Evaluation</h3>
          <p className="text-[11px] text-muted-foreground">针对 {target} 的自动评分</p>
        </div>
        <span
          className={cn(
            "rounded border px-2 py-0.5 text-[11px] font-medium",
            VERDICT_STYLE[verdict] || "border-border text-muted-foreground",
          )}
        >
          {verdict}
        </span>
      </div>

      <div className="rounded border border-border/60 bg-muted/20 px-3 py-2">
        <div className="flex items-baseline justify-between">
          <span className="text-muted-foreground">综合分</span>
          <span className="text-lg font-semibold text-foreground">
            {evaluation.overall ?? "—"}
            <span className="text-xs font-normal text-muted-foreground">/10</span>
          </span>
        </div>
        {evaluation.summary && (
          <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
            {evaluation.summary}
          </p>
        )}
      </div>

      <div className="space-y-1.5">
        {Object.entries(DIM_LABELS).map(([key, label]) => {
          const score = Number((scores as Record<string, number>)[key] ?? 0);
          const pct = Math.max(0, Math.min(100, (score / 10) * 100));
          return (
            <div key={key}>
              <div className="mb-0.5 flex justify-between text-[11px]">
                <span className="text-muted-foreground">{label}</span>
                <span className="text-foreground/80">{score}/10</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-secondary">
                <div
                  className="h-full rounded-full bg-primary/80 transition-all"
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>

      {(evaluation.highlights?.length || 0) > 0 && (
        <div>
          <div className="mb-0.5 text-[11px] font-medium text-foreground">亮点</div>
          <ul className="list-disc space-y-0.5 pl-4 text-[11px] text-muted-foreground">
            {evaluation.highlights!.slice(0, 4).map((h, i) => (
              <li key={i}>{h}</li>
            ))}
          </ul>
        </div>
      )}

      {(evaluation.gaps?.length || 0) > 0 && (
        <div>
          <div className="mb-0.5 text-[11px] font-medium text-foreground">缺口</div>
          <ul className="list-disc space-y-0.5 pl-4 text-[11px] text-muted-foreground">
            {evaluation.gaps!.slice(0, 4).map((g, i) => (
              <li key={i}>{g}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
