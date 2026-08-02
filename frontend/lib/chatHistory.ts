/**
 * Local chat history: projects → conversations → messages.
 * Persisted in localStorage (browser only).
 */

import type { Message } from "./types";

const STORAGE_KEY = "pm-copilot-history-v1";

export interface StoredMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  agentName?: string;
  timestamp: string;
  metadata?: Record<string, unknown>;
}

export interface Conversation {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: StoredMessage[];
  sessionId: string | null;
  decisionDone?: boolean;
  awaitingClarification?: boolean;
  clarifyResumePhase?: string;
}

export interface Project {
  id: string;
  name: string;
  createdAt: string;
  updatedAt: string;
  conversations: Conversation[];
}

export interface HistoryStore {
  version: 1;
  projects: Project[];
  activeProjectId: string | null;
  activeConversationId: string | null;
}

export const WELCOME_MESSAGE: Message = {
  id: "welcome",
  role: "assistant",
  content:
    "你好！我是 PM Copilot，你的 AI 产品经理助手。\n\n我可以帮你：\n- 🔍 **分析需求**：不清楚时会逐步确认，再给出 GO/PIVOT/KILL\n- 📄 **生成 PRD**：输出结构化产品需求文档，并经质量审查\n- 🚀 **完整流程**：决策 → PRD → Critic → 压力测试\n- ⚡ **压力测试**：从 5 个关键角色视角挑战方案\n\n试试输入你的产品需求，或点击下方快捷操作。",
  timestamp: new Date(),
};

const DEFAULT_PROJECT_NAMES = new Set(["默认项目", "未命名项目", "新项目"]);
const IGNORE_FOR_TITLE_RE =
  /^(请帮我(分析需求|生成 PRD|完整流程|压力测试)|请基于刚才|请基于当前|跳过，直接决策|__SKIP_CLARIFY__)/;

function uid(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export function serializeMessages(messages: Message[]): StoredMessage[] {
  return messages.map((m) => ({
    id: m.id,
    role: m.role,
    content: m.content,
    agentName: m.agentName,
    timestamp:
      m.timestamp instanceof Date
        ? m.timestamp.toISOString()
        : new Date(m.timestamp).toISOString(),
    metadata: m.metadata,
  }));
}

export function deserializeMessages(messages: StoredMessage[]): Message[] {
  return messages.map((m) => ({
    id: m.id,
    role: m.role,
    content: m.content,
    agentName: m.agentName as Message["agentName"],
    timestamp: new Date(m.timestamp),
    metadata: m.metadata,
  }));
}

function shortenTitle(text: string, max = 28): string {
  const t = text.replace(/\s+/g, " ").trim();
  if (!t) return "新对话";
  return t.length > max ? `${t.slice(0, max)}…` : t;
}

/** Prefer a real product idea over quick-action buttons for naming. */
export function titleFromMessages(messages: Message[] | StoredMessage[]): string {
  const userMsgs = messages.filter(
    (m) => m.role === "user" && m.content.trim() && m.content !== "__SKIP_CLARIFY__",
  );
  if (userMsgs.length === 0) return "新对话";

  const substantive = userMsgs.find(
    (m) => !IGNORE_FOR_TITLE_RE.test(m.content.trim()),
  );
  return shortenTitle((substantive || userMsgs[0]).content);
}

export function isDefaultProjectName(name: string): boolean {
  return DEFAULT_PROJECT_NAMES.has(name.trim());
}

function emptyStore(): HistoryStore {
  const project = createProject("默认项目");
  const conversation = createConversation();
  project.conversations = [conversation];
  return {
    version: 1,
    projects: [project],
    activeProjectId: project.id,
    activeConversationId: conversation.id,
  };
}

export function createProject(name: string): Project {
  const now = new Date().toISOString();
  return {
    id: uid("proj"),
    name: name.trim() || "未命名项目",
    createdAt: now,
    updatedAt: now,
    conversations: [],
  };
}

export function createConversation(): Conversation {
  const now = new Date().toISOString();
  return {
    id: uid("chat"),
    title: "新对话",
    createdAt: now,
    updatedAt: now,
    messages: serializeMessages([WELCOME_MESSAGE]),
    sessionId: null,
    decisionDone: false,
    awaitingClarification: false,
    clarifyResumePhase: "decision",
  };
}

export function loadHistoryStore(): HistoryStore {
  if (typeof window === "undefined") return emptyStore();
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return emptyStore();
    const parsed = JSON.parse(raw) as HistoryStore;
    if (!parsed?.projects?.length) return emptyStore();
    return parsed;
  } catch {
    return emptyStore();
  }
}

export function saveHistoryStore(store: HistoryStore): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  } catch (e) {
    console.warn("Failed to save chat history", e);
  }
}

export function getActiveConversation(store: HistoryStore): Conversation | null {
  const project = store.projects.find((p) => p.id === store.activeProjectId);
  if (!project) return null;
  return (
    project.conversations.find((c) => c.id === store.activeConversationId) ||
    null
  );
}

/** Upsert current conversation snapshot; auto-name chat + project after user speaks. */
export function persistActiveConversation(
  store: HistoryStore,
  patch: Partial<
    Pick<
      Conversation,
      | "messages"
      | "sessionId"
      | "decisionDone"
      | "awaitingClarification"
      | "clarifyResumePhase"
      | "title"
    >
  > & { messages?: StoredMessage[] },
): HistoryStore {
  const now = new Date().toISOString();
  const projects = store.projects.map((p) => {
    if (p.id !== store.activeProjectId) return p;

    let autoProjectName: string | null = null;

    const conversations = p.conversations.map((c) => {
      if (c.id !== store.activeConversationId) return c;
      const messages = patch.messages ?? c.messages;
      const hasUser = messages.some((m) => m.role === "user");
      const autoTitle = hasUser ? titleFromMessages(messages) : c.title;
      const title = patch.title || autoTitle;

      // Rename project once when it still has a placeholder name
      if (
        hasUser &&
        isDefaultProjectName(p.name) &&
        title &&
        title !== "新对话"
      ) {
        autoProjectName = title;
      }

      return {
        ...c,
        ...patch,
        messages,
        title,
        updatedAt: now,
      };
    });

    return {
      ...p,
      name: autoProjectName || p.name,
      conversations,
      updatedAt: now,
    };
  });
  return { ...store, projects };
}

export function selectConversation(
  store: HistoryStore,
  projectId: string,
  conversationId: string,
): HistoryStore {
  return {
    ...store,
    activeProjectId: projectId,
    activeConversationId: conversationId,
  };
}

export function addConversationToProject(
  store: HistoryStore,
  projectId: string,
): HistoryStore {
  const conversation = createConversation();
  const projects = store.projects.map((p) => {
    if (p.id !== projectId) return p;
    return {
      ...p,
      conversations: [conversation, ...p.conversations],
      updatedAt: new Date().toISOString(),
    };
  });
  return {
    ...store,
    projects,
    activeProjectId: projectId,
    activeConversationId: conversation.id,
  };
}

export function addProject(store: HistoryStore, name: string): HistoryStore {
  const project = createProject(name);
  const conversation = createConversation();
  project.conversations = [conversation];
  return {
    ...store,
    projects: [project, ...store.projects],
    activeProjectId: project.id,
    activeConversationId: conversation.id,
  };
}

export function renameProject(
  store: HistoryStore,
  projectId: string,
  name: string,
): HistoryStore {
  const trimmed = name.trim();
  if (!trimmed) return store;
  return {
    ...store,
    projects: store.projects.map((p) =>
      p.id === projectId
        ? { ...p, name: trimmed, updatedAt: new Date().toISOString() }
        : p,
    ),
  };
}

export function deleteConversation(
  store: HistoryStore,
  projectId: string,
  conversationId: string,
): HistoryStore {
  let nextActiveConv = store.activeConversationId;
  let nextActiveProj = store.activeProjectId;

  const projects = store.projects.map((p) => {
    if (p.id !== projectId) return p;
    const conversations = p.conversations.filter((c) => c.id !== conversationId);
    if (conversations.length === 0) {
      const fresh = createConversation();
      conversations.push(fresh);
    }
    if (store.activeConversationId === conversationId) {
      nextActiveConv = conversations[0].id;
      nextActiveProj = p.id;
    }
    return { ...p, conversations, updatedAt: new Date().toISOString() };
  });

  return {
    ...store,
    projects,
    activeProjectId: nextActiveProj,
    activeConversationId: nextActiveConv,
  };
}

export function deleteProject(store: HistoryStore, projectId: string): HistoryStore {
  let projects = store.projects.filter((p) => p.id !== projectId);
  if (projects.length === 0) {
    return emptyStore();
  }
  let activeProjectId = store.activeProjectId;
  let activeConversationId = store.activeConversationId;
  if (activeProjectId === projectId) {
    activeProjectId = projects[0].id;
    activeConversationId = projects[0].conversations[0]?.id ?? null;
    if (!activeConversationId) {
      const conv = createConversation();
      projects = projects.map((p, i) =>
        i === 0 ? { ...p, conversations: [conv] } : p,
      );
      activeConversationId = conv.id;
    }
  }
  return { ...store, projects, activeProjectId, activeConversationId };
}
