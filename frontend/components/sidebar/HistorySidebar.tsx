"use client";

import { useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import type { HistoryStore, Project } from "@/lib/chatHistory";

interface HistorySidebarProps {
  store: HistoryStore;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
  onNewChat: () => void;
  onNewProject: (name: string) => void;
  onSelectConversation: (projectId: string, conversationId: string) => void;
  onDeleteConversation: (projectId: string, conversationId: string) => void;
  onDeleteProject: (projectId: string) => void;
  onRenameProject: (projectId: string, name: string) => void;
}

export function HistorySidebar({
  store,
  collapsed,
  onToggleCollapsed,
  onNewChat,
  onNewProject,
  onSelectConversation,
  onDeleteConversation,
  onDeleteProject,
  onRenameProject,
}: HistorySidebarProps) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>(() => {
    const init: Record<string, boolean> = {};
    for (const p of store.projects) init[p.id] = true;
    return init;
  });
  const [creatingProject, setCreatingProject] = useState(false);
  const [projectName, setProjectName] = useState("");
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  const projects = useMemo(
    () =>
      [...store.projects].sort(
        (a, b) =>
          new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
      ),
    [store.projects],
  );

  if (collapsed) {
    return (
      <aside className="flex w-12 flex-col items-center border-r border-border bg-[#0c0f14] py-3">
        <button
          type="button"
          onClick={onToggleCollapsed}
          className="rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground"
          title="展开历史"
        >
          <SidebarIcon />
        </button>
        <button
          type="button"
          onClick={onNewChat}
          className="mt-2 rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground"
          title="新对话"
        >
          <PlusIcon />
        </button>
      </aside>
    );
  }

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-border bg-[#0c0f14]">
      <div className="flex items-center justify-between gap-2 px-3 py-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-foreground">
            PM Copilot
          </div>
          <div className="truncate text-[10px] text-muted-foreground">
            AI 产品经理助手
          </div>
        </div>
        <button
          type="button"
          onClick={onToggleCollapsed}
          className="shrink-0 rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
          title="收起"
        >
          <SidebarIcon />
        </button>
      </div>

      <div className="space-y-1.5 px-2 pb-2">
        <button
          type="button"
          onClick={onNewChat}
          className="flex w-full items-center gap-2 rounded-md border border-border/80 bg-transparent px-2.5 py-2 text-left text-xs text-foreground transition-colors hover:bg-accent"
        >
          <PlusIcon />
          新对话
        </button>
        <button
          type="button"
          onClick={() => {
            setCreatingProject(true);
            setProjectName("");
          }}
          className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <FolderPlusIcon />
          新建项目
        </button>
      </div>

      {creatingProject && (
        <div className="space-y-1.5 border-b border-border px-2 pb-2">
          <input
            autoFocus
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && projectName.trim()) {
                onNewProject(projectName.trim());
                setCreatingProject(false);
              }
              if (e.key === "Escape") setCreatingProject(false);
            }}
            placeholder="项目名称…"
            className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-xs text-foreground outline-none focus:border-ring"
          />
          <div className="flex gap-1">
            <button
              type="button"
              className="flex-1 rounded bg-primary px-2 py-1 text-[11px] text-primary-foreground"
              onClick={() => {
                if (!projectName.trim()) return;
                onNewProject(projectName.trim());
                setCreatingProject(false);
              }}
            >
              创建
            </button>
            <button
              type="button"
              className="rounded border border-border px-2 py-1 text-[11px] text-muted-foreground"
              onClick={() => setCreatingProject(false)}
            >
              取消
            </button>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-2 pb-3 pt-1">
        <p className="mb-1.5 px-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground/80">
          项目
        </p>
        <div className="space-y-1">
          {projects.map((project) => (
            <ProjectBlock
              key={project.id}
              project={project}
              activeProjectId={store.activeProjectId}
              activeConversationId={store.activeConversationId}
              expanded={expanded[project.id] !== false}
              renaming={renamingId === project.id}
              renameValue={renameValue}
              onToggleExpand={() =>
                setExpanded((prev) => ({
                  ...prev,
                  [project.id]: !(prev[project.id] !== false),
                }))
              }
              onSelectConversation={onSelectConversation}
              onDeleteConversation={onDeleteConversation}
              onDeleteProject={onDeleteProject}
              onStartRename={() => {
                setRenamingId(project.id);
                setRenameValue(project.name);
              }}
              onRenameChange={setRenameValue}
              onRenameCommit={() => {
                if (renameValue.trim()) {
                  onRenameProject(project.id, renameValue.trim());
                }
                setRenamingId(null);
              }}
              onRenameCancel={() => setRenamingId(null)}
            />
          ))}
        </div>
      </div>

      <div className="border-t border-border px-3 py-2 text-[10px] text-muted-foreground">
        对话保存在本机浏览器
      </div>
    </aside>
  );
}

function ProjectBlock({
  project,
  activeProjectId,
  activeConversationId,
  expanded,
  renaming,
  renameValue,
  onToggleExpand,
  onSelectConversation,
  onDeleteConversation,
  onDeleteProject,
  onStartRename,
  onRenameChange,
  onRenameCommit,
  onRenameCancel,
}: {
  project: Project;
  activeProjectId: string | null;
  activeConversationId: string | null;
  expanded: boolean;
  renaming: boolean;
  renameValue: string;
  onToggleExpand: () => void;
  onSelectConversation: (projectId: string, conversationId: string) => void;
  onDeleteConversation: (projectId: string, conversationId: string) => void;
  onDeleteProject: (projectId: string) => void;
  onStartRename: () => void;
  onRenameChange: (v: string) => void;
  onRenameCommit: () => void;
  onRenameCancel: () => void;
}) {
  const conversations = [...project.conversations].sort(
    (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
  );
  const isActiveProject = project.id === activeProjectId;

  return (
    <div className="rounded-md">
      <div
        className={cn(
          "group flex items-center gap-1 rounded-md px-1.5 py-1",
          isActiveProject && "bg-accent/40",
        )}
      >
        <button
          type="button"
          onClick={onToggleExpand}
          className="shrink-0 text-muted-foreground hover:text-foreground"
          aria-label={expanded ? "折叠" : "展开"}
        >
          <ChevronIcon open={expanded} />
        </button>

        {renaming ? (
          <input
            autoFocus
            value={renameValue}
            onChange={(e) => onRenameChange(e.target.value)}
            onBlur={onRenameCommit}
            onKeyDown={(e) => {
              if (e.key === "Enter") onRenameCommit();
              if (e.key === "Escape") onRenameCancel();
            }}
            className="min-w-0 flex-1 rounded border border-border bg-background px-1 py-0.5 text-xs outline-none"
          />
        ) : (
          <button
            type="button"
            onClick={onToggleExpand}
            onDoubleClick={onStartRename}
            className="min-w-0 flex-1 truncate text-left text-xs font-medium text-foreground"
            title="双击重命名"
          >
            {project.name}
          </button>
        )}

        <button
          type="button"
          onClick={() => {
            if (
              confirm(
                `删除项目「${project.name}」及其全部对话？此操作不可恢复。`,
              )
            ) {
              onDeleteProject(project.id);
            }
          }}
          className="shrink-0 rounded p-0.5 text-muted-foreground opacity-0 hover:text-red-400 group-hover:opacity-100"
          title="删除项目"
        >
          <TrashIcon />
        </button>
      </div>

      {expanded && (
        <ul className="ml-2 space-y-0.5 border-l border-border/50 pl-2 py-0.5">
          {conversations.map((c) => {
            const active =
              project.id === activeProjectId &&
              c.id === activeConversationId;
            return (
              <li key={c.id} className="group/chat relative">
                <button
                  type="button"
                  onClick={() => onSelectConversation(project.id, c.id)}
                  className={cn(
                    "w-full rounded-md px-2 py-1.5 pr-7 text-left text-xs transition-colors",
                    active
                      ? "bg-accent text-foreground"
                      : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                  )}
                >
                  <span className="line-clamp-2 leading-snug">{c.title}</span>
                </button>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (confirm(`删除对话「${c.title}」？`)) {
                      onDeleteConversation(project.id, c.id);
                    }
                  }}
                  className="absolute right-1 top-1/2 -translate-y-1/2 rounded p-0.5 text-muted-foreground opacity-0 hover:text-red-400 group-hover/chat:opacity-100"
                  title="删除对话"
                >
                  <TrashIcon />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function SidebarIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M9 3v18" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function FolderPlusIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 10v6M9 13h6" />
      <path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9l-.81-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z" />
    </svg>
  );
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      className={cn("transition-transform", open && "rotate-90")}
    >
      <path d="m9 18 6-6-6-6" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6" />
    </svg>
  );
}
