"use client";

import { useCallback, useEffect, useState } from "react";
import {
  uploadMemoryDoc,
  listMemoryDocs,
  deleteMemoryDoc,
  getOrgProfile,
  rebuildOrgProfile,
} from "@/lib/api";
import type { MemoryCitation, MemoryDoc, OrgProfile } from "@/lib/types";

interface MemoryPanelProps {
  citations?: MemoryCitation[];
}

const DOC_TYPES = [
  { value: "prd", label: "PRD" },
  { value: "decision", label: "决策" },
  { value: "stress_test", label: "复盘/压力测试" },
  { value: "meeting_note", label: "会议纪要" },
  { value: "other", label: "其他" },
];

export function MemoryPanel({ citations = [] }: MemoryPanelProps) {
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

  return (
    <div className="space-y-3 text-xs">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-xs font-semibold text-foreground">组织记忆</h3>
          <p className="text-[11px] text-muted-foreground">
            文档 {Number(stats.document_count ?? docs.length)} · 切片{" "}
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

      {error && (
        <div className="rounded border border-red-500/40 bg-red-500/10 px-2 py-1 text-[11px] text-red-300">
          {error}
        </div>
      )}

      {citations.length > 0 && (
        <div className="rounded border border-border bg-secondary/40 p-2">
          <p className="mb-1 font-medium text-foreground">本次检索引用</p>
          <ul className="space-y-1">
            {citations.slice(0, 5).map((c, i) => (
              <li key={c.chunk_id || `${c.doc_id}-${i}`} className="text-muted-foreground">
                <span className="text-foreground">
                  [{c.index ?? i + 1}] {c.title || "Untitled"}
                </span>
                {typeof c.score === "number" && (
                  <span className="ml-1">({c.score.toFixed(2)})</span>
                )}
                {c.preview && (
                  <div className="truncate text-[10px] opacity-80">{c.preview}</div>
                )}
              </li>
            ))}
          </ul>
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
