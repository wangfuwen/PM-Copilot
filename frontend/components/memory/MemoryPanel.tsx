"use client";

import { useCallback, useEffect, useState } from "react";
import {
  uploadMemoryDoc,
  listMemoryDocs,
  deleteMemoryDoc,
  getOrgProfile,
  rebuildOrgProfile,
  getMemoryChunk,
} from "@/lib/api";
import type { MemoryCitation, MemoryChunk, MemoryDoc, OrgProfile } from "@/lib/types";

interface MemoryPanelProps {
  citations?: MemoryCitation[];
  memoryEmpty?: boolean;
}

const DOC_TYPES = [
  { value: "prd", label: "PRD" },
  { value: "decision", label: "决策" },
  { value: "stress_test", label: "复盘/压力测试" },
  { value: "meeting_note", label: "会议纪要" },
  { value: "other", label: "其他" },
];

export function MemoryPanel({ citations = [], memoryEmpty = false }: MemoryPanelProps) {
  const [docs, setDocs] = useState<MemoryDoc[]>([]);
  const [stats, setStats] = useState<Record<string, unknown>>({});
  const [profile, setProfile] = useState<OrgProfile | null>(null);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [docType, setDocType] = useState("prd");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showProfile, setShowProfile] = useState(false);
  const [showUpload, setShowUpload] = useState(false);
  const [preview, setPreview] = useState<MemoryChunk | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [docsRes, profileRes] = await Promise.all([
        listMemoryDocs(),
        getOrgProfile(),
      ]);
      setDocs(docsRes.documents || []);
      setStats(docsRes.stats || {});
      setProfile(profileRes.profile || null);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const openCitation = async (c: MemoryCitation) => {
    if (!c.chunk_id) {
      setError("该引用缺少 chunk_id，无法打开原文");
      return;
    }
    setPreviewLoading(true);
    setError(null);
    try {
      const chunk = await getMemoryChunk(c.chunk_id);
      setPreview(chunk);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleUpload = async () => {
    if (!title.trim() || !content.trim()) {
      setError("请填写标题和 Markdown 内容");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await uploadMemoryDoc(content, title.trim(), docType, true);
      setTitle("");
      setContent("");
      setShowUpload(false);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const handleFile = async (file: File | null) => {
    if (!file) return;
    const text = await file.text();
    setContent(text);
    if (!title.trim()) {
      setTitle(file.name.replace(/\.md$/i, ""));
    }
    setShowUpload(true);
  };

  const handleDelete = async (docId: string) => {
    setBusy(true);
    try {
      await deleteMemoryDoc(docId);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const handleRebuild = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await rebuildOrgProfile();
      setProfile(res.profile);
      setShowProfile(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const mapping = profile?.terminology?.mapping || {};
  const lessons = profile?.lessons_learned || [];
  const isEmptyKb =
    memoryEmpty || Number(stats.document_count ?? docs.length) === 0;

  return (
    <div className="space-y-3 text-xs">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-xs font-semibold text-foreground">组织记忆</h3>
          <p className="text-[11px] text-muted-foreground">
            仅上传入库 · 文档 {Number(stats.document_count ?? docs.length)} · 切片{" "}
            {Number(stats.chunk_count ?? 0)}
          </p>
        </div>
        <div className="flex gap-1">
          <button
            onClick={() => setShowUpload((v) => !v)}
            className="rounded border border-border px-2 py-1 text-[11px] hover:bg-accent"
            disabled={busy}
          >
            上传
          </button>
          <button
            onClick={handleRebuild}
            className="rounded border border-border px-2 py-1 text-[11px] hover:bg-accent"
            disabled={busy || docs.length === 0}
          >
            重建画像
          </button>
        </div>
      </div>

      {isEmptyKb && (
        <div className="rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1.5 text-[11px] text-amber-200">
          知识库为空：Agent 将在无组织上下文下运行。请上传历史 PRD / 复盘以启用 RAG。
        </div>
      )}

      {error && (
        <div className="rounded border border-red-500/40 bg-red-500/10 px-2 py-1 text-[11px] text-red-300">
          {error}
        </div>
      )}

      {citations.length > 0 && (
        <CitationSideList
          citations={citations}
          onOpen={openCitation}
          busy={previewLoading}
        />
      )}

      {preview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="max-h-[80vh] w-full max-w-lg overflow-hidden rounded-lg border border-border bg-card shadow-xl">
            <div className="flex items-start justify-between border-b border-border px-4 py-3">
              <div className="min-w-0 pr-3">
                <h4 className="truncate text-sm font-semibold text-foreground">
                  {preview.title}
                </h4>
                <p className="text-[11px] text-muted-foreground">
                  {preview.doc_type}
                  {preview.section_title ? ` · ${preview.section_title}` : ""}
                </p>
              </div>
              <button
                onClick={() => setPreview(null)}
                className="rounded border border-border px-2 py-1 text-[11px] hover:bg-accent"
              >
                关闭
              </button>
            </div>
            <div className="max-h-[60vh] overflow-y-auto whitespace-pre-wrap px-4 py-3 text-xs leading-relaxed text-foreground">
              {preview.content}
            </div>
          </div>
        </div>
      )}

      {showUpload && (
        <div className="space-y-2 rounded border border-border p-2">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="文档标题"
            className="w-full rounded border border-border bg-background px-2 py-1 text-[11px]"
          />
          <select
            value={docType}
            onChange={(e) => setDocType(e.target.value)}
            className="w-full rounded border border-border bg-background px-2 py-1 text-[11px]"
          >
            {DOC_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="粘贴 Markdown 内容..."
            rows={6}
            className="w-full rounded border border-border bg-background px-2 py-1 text-[11px]"
          />
          <div className="flex items-center justify-between gap-2">
            <label className="cursor-pointer text-[11px] text-muted-foreground underline">
              选择 .md 文件
              <input
                type="file"
                accept=".md,text/markdown,text/plain"
                className="hidden"
                onChange={(e) => handleFile(e.target.files?.[0] || null)}
              />
            </label>
            <button
              onClick={handleUpload}
              disabled={busy}
              className="rounded bg-primary px-3 py-1 text-[11px] text-primary-foreground disabled:opacity-50"
            >
              {busy ? "上传中..." : "入库并更新画像"}
            </button>
          </div>
        </div>
      )}

      <div className="max-h-36 space-y-1 overflow-y-auto">
        {docs.length === 0 ? (
          <p className="text-muted-foreground">知识库为空，先上传几份历史 PRD / 复盘。</p>
        ) : (
          docs.map((d) => (
            <div
              key={d.doc_id}
              className="flex items-start justify-between gap-2 rounded border border-border/60 px-2 py-1"
            >
              <div className="min-w-0">
                <div className="truncate font-medium text-foreground">{d.title}</div>
                <div className="text-[10px] text-muted-foreground">
                  {d.doc_type} · {d.chunk_count || 1} chunks
                </div>
              </div>
              <button
                onClick={() => handleDelete(d.doc_id)}
                className="shrink-0 text-[10px] text-muted-foreground hover:text-red-400"
                disabled={busy}
              >
                删除
              </button>
            </div>
          ))
        )}
      </div>

      <div>
        <button
          onClick={() => setShowProfile((v) => !v)}
          className="text-[11px] text-muted-foreground hover:text-foreground"
        >
          {showProfile ? "收起" : "展开"} Org Profile
          {lessons.length > 0 ? ` · ${lessons.length} 条踩坑` : ""}
        </button>
        {showProfile && (
          <div className="mt-1 max-h-40 space-y-1 overflow-y-auto rounded border border-border p-2 text-[11px] text-muted-foreground">
            {Object.keys(mapping).length > 0 && (
              <div>
                <div className="font-medium text-foreground">术语映射</div>
                {Object.entries(mapping).slice(0, 8).map(([k, v]) => (
                  <div key={k}>
                    {k} → {v}
                  </div>
                ))}
              </div>
            )}
            {lessons.length > 0 && (
              <div>
                <div className="font-medium text-foreground">踩坑清单</div>
                <ul className="list-disc pl-4">
                  {lessons.slice(0, 5).map((l, i) => (
                    <li key={i}>{l}</li>
                  ))}
                </ul>
              </div>
            )}
            {Object.keys(mapping).length === 0 && lessons.length === 0 && (
              <p>画像为空。上传文档后点击「重建画像」。</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/** Side-panel citation list: muted, collapsed by default, click to open source. */
function CitationSideList({
  citations,
  onOpen,
  busy,
}: {
  citations: MemoryCitation[];
  onOpen: (c: MemoryCitation) => void;
  busy: boolean;
}) {
  const [collapsed, setCollapsed] = useState(true);
  const items = (() => {
    const map = new Map<string, MemoryCitation>();
    for (const c of citations) {
      const key = c.doc_id || c.chunk_id || c.title || "";
      const prev = map.get(key);
      if (!prev || (c.score ?? 0) > (prev.score ?? 0)) map.set(key, c);
    }
    return Array.from(map.values())
      .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
      .slice(0, 5);
  })();

  return (
    <div className="rounded border border-border/60 bg-muted/20 p-2 text-muted-foreground">
      <button
        type="button"
        onClick={() => setCollapsed((v) => !v)}
        className="flex w-full items-center justify-between text-left"
      >
        <span className="font-medium text-foreground/80">
          本次引用 · {items.length}
        </span>
        <span className="text-[10px]">{collapsed ? "展开" : "收起"}</span>
      </button>
      {!collapsed && (
        <ul className="mt-1.5 space-y-1 border-t border-border/40 pt-1.5">
          {items.map((c, i) => (
            <li key={c.chunk_id || `${c.doc_id}-${i}`}>
              <button
                type="button"
                onClick={() => onOpen(c)}
                className="w-full text-left hover:text-foreground"
                disabled={busy}
              >
                <span className="text-foreground/90 underline-offset-2 hover:underline">
                  [{i + 1}] {c.title || "Untitled"}
                </span>
                {typeof c.score === "number" && (
                  <span className="ml-1 text-[10px]">
                    ({(c.score * 100).toFixed(0)}%)
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
