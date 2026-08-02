"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import type { MemoryCitation } from "@/lib/types";

interface MemoryCitationsBlockProps {
  citations: MemoryCitation[];
  defaultCollapsed?: boolean;
}

/** Compact, collapsible org-memory citations (muted style, not error/red). */
export function MemoryCitationsBlock({
  citations,
  defaultCollapsed = true,
}: MemoryCitationsBlockProps) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  const items = dedupeCitations(citations).slice(0, 5);

  if (items.length === 0) return null;

  return (
    <div className="rounded-lg border border-border/60 bg-muted/30 px-3 py-2">
      <button
        type="button"
        onClick={() => setCollapsed((v) => !v)}
        className="flex w-full items-center justify-between gap-2 text-left"
      >
        <span className="text-xs font-medium text-muted-foreground">
          组织记忆检索 · {items.length} 条引用
        </span>
        <span className="text-[11px] text-muted-foreground">
          {collapsed ? "展开" : "收起"}
        </span>
      </button>

      {!collapsed && (
        <ul className="mt-2 space-y-2 border-t border-border/50 pt-2">
          {items.map((c, i) => (
            <li key={c.chunk_id || `${c.doc_id}-${i}`} className="text-xs">
              <div className="font-medium text-foreground/90">
                {i + 1}. {c.title || "Untitled"}
                <span className="ml-1 font-normal text-muted-foreground">
                  ({c.doc_type || "doc"}
                  {typeof c.score === "number"
                    ? ` · ${(c.score * 100).toFixed(0)}%`
                    : ""}
                  )
                </span>
              </div>
              {c.preview && (
                <p className="mt-0.5 line-clamp-2 text-[11px] leading-relaxed text-muted-foreground">
                  {cleanPreview(c.preview)}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
      {collapsed && (
        <p className="mt-1 text-[11px] text-muted-foreground">
          点击展开查看检索片段；右侧面板可点开原文。
        </p>
      )}
    </div>
  );
}

function dedupeCitations(citations: MemoryCitation[]): MemoryCitation[] {
  const byKey = new Map<string, MemoryCitation>();
  for (const c of citations) {
    const key = c.doc_id || c.chunk_id || c.title || JSON.stringify(c);
    const prev = byKey.get(key);
    if (!prev || (c.score ?? 0) > (prev.score ?? 0)) {
      byKey.set(key, c);
    }
  }
  return Array.from(byKey.values()).sort(
    (a, b) => (b.score ?? 0) - (a.score ?? 0),
  );
}

function cleanPreview(preview: string): string {
  return preview
    .replace(/^#+\s*/gm, "")
    .replace(/\s+/g, " ")
    .trim();
}

export function citationsSummaryLabel(citations: MemoryCitation[]): string {
  const n = dedupeCitations(citations).length;
  return `检索到 ${n} 条组织记忆引用`;
}
