"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { ChatWindow } from "@/components/chat/ChatWindow";
import { InputBar } from "@/components/chat/InputBar";
import { AgentStatus } from "@/components/agents/AgentStatus";
import { AgentTimeline } from "@/components/agents/AgentTimeline";
import { MemoryPanel } from "@/components/memory/MemoryPanel";
import { HistorySidebar } from "@/components/sidebar/HistorySidebar";
import { SKIP_CLARIFY_TOKEN } from "@/components/chat/ClarifyOptions";
import {
  WELCOME_MESSAGE,
  loadHistoryStore,
  saveHistoryStore,
  getActiveConversation,
  persistActiveConversation,
  selectConversation,
  addConversationToProject,
  addProject,
  deleteConversation,
  deleteProject,
  renameProject,
  serializeMessages,
  deserializeMessages,
  type HistoryStore,
} from "@/lib/chatHistory";
import type {
  Message,
  AgentState,
  WorkflowPhase,
  SSEEvent,
  MemoryCitation,
  ClarifyStep,
  CriticFeedback,
  AgentName,
} from "@/lib/types";

const QUICK_ACTIONS = [
  { id: "analyze", label: "分析需求", description: "5W1H 分析 + 决策建议", phase: "decision" as const, icon: "🔍" },
  { id: "prd", label: "生成 PRD", description: "结构化产品需求文档", phase: "prd_generation" as const, icon: "📄" },
  { id: "full", label: "完整流程", description: "决策 → PRD → 审查 → 压力测试", phase: "full_pipeline" as const, icon: "🚀" },
  { id: "stress", label: "压力测试", description: "5 角色红队挑战", phase: "stress_test" as const, icon: "⚡" },
];

function applyConversationToState(
  store: HistoryStore,
  setters: {
    setMessages: (m: Message[]) => void;
    setSessionId: (s: string | null) => void;
    setDecisionDone: (v: boolean) => void;
    setAwaitingClarification: (v: boolean) => void;
    setClarifyResumePhase: (v: string) => void;
    setAgents: (a: AgentState[]) => void;
    setPhase: (p: WorkflowPhase) => void;
    setCitations: (c: MemoryCitation[]) => void;
    setIsLoading: (v: boolean) => void;
  },
) {
  const conv = getActiveConversation(store);
  if (!conv) {
    setters.setMessages([{ ...WELCOME_MESSAGE, timestamp: new Date() }]);
    return;
  }
  setters.setMessages(deserializeMessages(conv.messages));
  setters.setSessionId(conv.sessionId);
  setters.setDecisionDone(Boolean(conv.decisionDone));
  setters.setAwaitingClarification(Boolean(conv.awaitingClarification));
  setters.setClarifyResumePhase(conv.clarifyResumePhase || "decision");
  setters.setAgents([]);
  setters.setPhase("idle");
  setters.setCitations([]);
  setters.setIsLoading(false);
}

export default function Home() {
  const [historyReady, setHistoryReady] = useState(false);
  const [historyStore, setHistoryStore] = useState<HistoryStore | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const [messages, setMessages] = useState<Message[]>([
    { ...WELCOME_MESSAGE, timestamp: new Date() },
  ]);
  const [agents, setAgents] = useState<AgentState[]>([]);
  const [phase, setPhase] = useState<WorkflowPhase>("idle");
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [citations, setCitations] = useState<MemoryCitation[]>([]);
  const [memoryEmpty, setMemoryEmpty] = useState(false);
  const [awaitingClarification, setAwaitingClarification] = useState(false);
  const [clarifyResumePhase, setClarifyResumePhase] = useState<string>("decision");
  const [demoMode, setDemoMode] = useState(true);
  const [rateLimitRemaining, setRateLimitRemaining] = useState<number | null>(null);
  const [decisionDone, setDecisionDone] = useState(false);
  const sendMessageRef = useRef<
    ((content: string, forcedPhase?: string) => Promise<void>) | null
  >(null);
  const skipNextPersist = useRef(false);

  // Hydrate history from localStorage
  useEffect(() => {
    const store = loadHistoryStore();
    setHistoryStore(store);
    skipNextPersist.current = true;
    applyConversationToState(store, {
      setMessages,
      setSessionId,
      setDecisionDone,
      setAwaitingClarification,
      setClarifyResumePhase,
      setAgents,
      setPhase,
      setCitations,
      setIsLoading,
    });
    setHistoryReady(true);
  }, []);

  // Persist active conversation whenever chat state changes
  useEffect(() => {
    if (!historyReady) return;
    if (skipNextPersist.current) {
      skipNextPersist.current = false;
      return;
    }
    setHistoryStore((prev) => {
      if (!prev) return prev;
      const next = persistActiveConversation(prev, {
        messages: serializeMessages(messages),
        sessionId,
        decisionDone,
        awaitingClarification,
        clarifyResumePhase,
      });
      saveHistoryStore(next);
      return next;
    });
  }, [
    messages,
    sessionId,
    decisionDone,
    awaitingClarification,
    clarifyResumePhase,
    historyReady,
  ]);

  const updateStore = useCallback((next: HistoryStore, loadActive = false) => {
    setHistoryStore(next);
    saveHistoryStore(next);
    if (loadActive) {
      skipNextPersist.current = true;
      applyConversationToState(next, {
        setMessages,
        setSessionId,
        setDecisionDone,
        setAwaitingClarification,
        setClarifyResumePhase,
        setAgents,
        setPhase,
        setCitations,
        setIsLoading,
      });
    }
  }, []);

  const handleNewChat = useCallback(() => {
    if (!historyStore?.activeProjectId) return;
    const next = addConversationToProject(
      historyStore,
      historyStore.activeProjectId,
    );
    updateStore(next, true);
  }, [historyStore, updateStore]);

  const handleNewProject = useCallback(
    (name: string) => {
      if (!historyStore) return;
      updateStore(addProject(historyStore, name), true);
    },
    [historyStore, updateStore],
  );

  const handleSelectConversation = useCallback(
    (projectId: string, conversationId: string) => {
      if (!historyStore) return;
      if (
        projectId === historyStore.activeProjectId &&
        conversationId === historyStore.activeConversationId
      ) {
        return;
      }
      // Flush current messages into store before switching
      const flushed = persistActiveConversation(historyStore, {
        messages: serializeMessages(messages),
        sessionId,
        decisionDone,
        awaitingClarification,
        clarifyResumePhase,
      });
      const next = selectConversation(flushed, projectId, conversationId);
      updateStore(next, true);
    },
    [
      historyStore,
      messages,
      sessionId,
      decisionDone,
      awaitingClarification,
      clarifyResumePhase,
      updateStore,
    ],
  );

  const handleDeleteConversation = useCallback(
    (projectId: string, conversationId: string) => {
      if (!historyStore) return;
      const next = deleteConversation(historyStore, projectId, conversationId);
      updateStore(next, true);
    },
    [historyStore, updateStore],
  );

  const handleDeleteProject = useCallback(
    (projectId: string) => {
      if (!historyStore) return;
      const next = deleteProject(historyStore, projectId);
      updateStore(next, true);
    },
    [historyStore, updateStore],
  );

  const handleRenameProject = useCallback(
    (projectId: string, name: string) => {
      if (!historyStore) return;
      updateStore(renameProject(historyStore, projectId, name), false);
    },
    [historyStore, updateStore],
  );

  const handleContinue = useCallback((nextPhase: string) => {
    const prompts: Record<string, string> = {
      prd_generation: "请基于刚才的决策结论继续生成 PRD",
      stress_test: "请基于当前方案做压力测试",
    };
    setMessages((prev) =>
      prev.filter((m) => m.metadata?.kind !== "continue_prompt"),
    );
    void sendMessageRef.current?.(
      prompts[nextPhase] || "请继续下一步",
      nextPhase,
    );
  }, []);

  const handleSendMessage = useCallback(
    async (content: string, forcedPhase?: string) => {
      const displayContent =
        content === SKIP_CLARIFY_TOKEN ? "跳过，直接决策" : content;

      const userMsg: Message = {
        id: `user-${Date.now()}`,
        role: "user",
        content: displayContent,
        timestamp: new Date(),
        metadata:
          content === SKIP_CLARIFY_TOKEN
            ? { raw: SKIP_CLARIFY_TOKEN }
            : undefined,
      };

      // Mark previous clarify steps as answered; drop stale continue prompts
      let baseMessages = messages
        .filter((m) => m.metadata?.kind !== "continue_prompt")
        .map((m) =>
          m.metadata?.clarify_step && !m.metadata?.clarify_answered
            ? {
                ...m,
                metadata: { ...m.metadata, clarify_answered: true },
              }
            : m,
        );
      const nextMessages = [...baseMessages, userMsg];
      setMessages(nextMessages);
      setIsLoading(true);

      const phaseToUse =
        forcedPhase ||
        (awaitingClarification ? clarifyResumePhase : "auto");

      const hadDecision =
        decisionDone ||
        messages.some(
          (m) =>
            m.agentName === "decision" &&
            m.role === "assistant" &&
            !m.metadata?.clarify_step &&
            (m.content || "").includes("决策建议"),
        );

      setAgents(buildInitialAgents(phaseToUse, agents, hadDecision));
      // Keep prior citations visible in side panel unless this turn replaces them
      setMemoryEmpty(false);

      const apiContent =
        content === SKIP_CLARIFY_TOKEN ||
        (userMsg.metadata?.raw as string | undefined) === SKIP_CLARIFY_TOKEN
          ? SKIP_CLARIFY_TOKEN
          : content;

      if (forcedPhase && !awaitingClarification) {
        setClarifyResumePhase(forcedPhase);
      }

      let timeoutId: ReturnType<typeof setTimeout> | undefined;
      let sawClarification = false;
      let sawDecision = false;
      let sawPrd = false;

      try {
        const { sendChatMessage } = await import("@/lib/api");

        // History must include the raw skip token for backend detection
        const messageHistory = nextMessages
          .filter(
            (m) =>
              m.role === "user" ||
              (m.role === "assistant" && !m.id.startsWith("welcome")),
          )
          .map((m) => {
            if (m.role === "user" && m.metadata?.raw === SKIP_CLARIFY_TOKEN) {
              return { role: m.role, content: SKIP_CLARIFY_TOKEN };
            }
            // For clarify assistant msgs, send the full history blob (with JSON)
            // which was stored in metadata.history_content if present
            if (m.metadata?.history_content) {
              return {
                role: m.role,
                content: String(m.metadata.history_content),
              };
            }
            return { role: m.role, content: m.content };
          });

        // Ensure last user message in history uses apiContent
        if (
          messageHistory.length > 0 &&
          messageHistory[messageHistory.length - 1].role === "user"
        ) {
          messageHistory[messageHistory.length - 1].content = apiContent;
        }

        timeoutId = setTimeout(() => {
          setIsLoading(false);
          setPhase("idle");
          setMessages((prev) => [
            ...prev,
            {
              id: `timeout-${Date.now()}`,
              role: "system",
              content:
                "⚠️ 请求超时：LLM 响应时间过长，请检查网络或 API Key 配置。",
              timestamp: new Date(),
            },
          ]);
        }, 180000);

        const newSessionId = await sendChatMessage(
          apiContent,
          sessionId,
          phaseToUse,
          (event: SSEEvent) => {
            clearTimeout(timeoutId);

            switch (event.type) {
              case "ping":
                if (typeof event.data.rate_limit_remaining === "number") {
                  setRateLimitRemaining(event.data.rate_limit_remaining);
                }
                break;

              case "agent_start":
                setAgents((prev) =>
                  prev.map((a) =>
                    a.name === event.data.agent
                      ? {
                          ...a,
                          status: "running" as const,
                          startedAt: new Date().toISOString(),
                        }
                      : a,
                  ),
                );
                setPhase((prev) => (prev === "idle" ? "decision" : prev));
                break;

              case "agent_output":
                if (event.data.output) {
                  const output = event.data.output as NonNullable<
                    SSEEvent["data"]["output"]
                  > & {
                    stress_test?: unknown;
                    stress_test_summary?: unknown;
                  };

                  if (output.memory_empty) {
                    setMemoryEmpty(true);
                  }

                  if (output.citations && output.citations.length > 0) {
                    setCitations(output.citations);
                    setMessages((prev) => [
                      ...prev.filter((m) => m.metadata?.kind !== "citations"),
                      {
                        id: `citations-${Date.now()}`,
                        role: "assistant",
                        content: "组织记忆检索",
                        agentName: "org_memory",
                        timestamp: new Date(),
                        metadata: {
                          kind: "citations",
                          citations: output.citations,
                        },
                      },
                    ]);
                  }

                  if (output.clarifying_questions) {
                    sawClarification = true;
                    setAwaitingClarification(true);
                    if (!awaitingClarification) {
                      // Free-form / auto ideas stop after decision; explicit full pipeline continues.
                      setClarifyResumePhase(
                        phaseToUse === "full_pipeline" ||
                          phaseToUse === "prd_generation"
                          ? phaseToUse
                          : "decision",
                      );
                    }
                    const step = output.clarifying_questions as ClarifyStep;
                    const historyContent = formatClarifyHistory(step);
                    setMessages((prev) => [
                      ...prev,
                      {
                        id: `clarify-${Date.now()}`,
                        role: "assistant",
                        content: step.question,
                        agentName: "decision",
                        timestamp: new Date(),
                        metadata: {
                          awaiting_clarification: true,
                          clarify_step: step,
                          clarify_answered: false,
                          history_content: historyContent,
                        },
                      },
                    ]);
                    setAgents((prev) =>
                      prev.map((a) =>
                        [
                          "prd_writer",
                          "critic",
                          "stress_test",
                          "memory_writeback",
                        ].includes(a.name)
                          ? { ...a, status: "skipped" as const }
                          : a,
                      ),
                    );
                  }

                  if (output.decision) {
                    sawDecision = true;
                    setDecisionDone(true);
                    setAwaitingClarification(false);
                    setMessages((prev) => [
                      ...prev,
                      {
                        id: `decision-${Date.now()}`,
                        role: "assistant",
                        content: formatDecisionOutput(output.decision),
                        agentName: "decision",
                        timestamp: new Date(),
                      },
                    ]);
                  }

                  if (output.prd) {
                    sawPrd = true;
                    setMessages((prev) => [
                      ...prev,
                      {
                        id: `prd-${Date.now()}`,
                        role: "assistant",
                        content: output.prd!,
                        agentName: "prd_writer",
                        timestamp: new Date(),
                      },
                    ]);
                  }

                  if (output.critic) {
                    setMessages((prev) => [
                      ...prev,
                      {
                        id: `critic-${Date.now()}`,
                        role: "assistant",
                        content: formatCriticOutput(output.critic!),
                        agentName: "critic",
                        timestamp: new Date(),
                      },
                    ]);
                  }

                  const stressTest = output.stressTest ?? output.stress_test;
                  const stressTestSummary =
                    output.stressTestSummary ?? output.stress_test_summary;
                  if (stressTest) {
                    setMessages((prev) => [
                      ...prev,
                      {
                        id: `stress-${Date.now()}`,
                        role: "assistant",
                        content: formatStressTestOutput(
                          stressTest as any[],
                          stressTestSummary,
                        ),
                        agentName: "stress_test",
                        timestamp: new Date(),
                      },
                    ]);
                  }
                }
                break;

              case "agent_complete": {
                const agentName = event.data.agent as AgentName | undefined;
                setAgents((prev) =>
                  prev.map((a) => {
                    if (a.name !== agentName) return a;
                    // Upload-only: writeback node is a no-op
                    if (agentName === "memory_writeback") {
                      return {
                        ...a,
                        status: "skipped" as const,
                        summary: "仅上传入库，不自动写入",
                        completedAt: new Date().toISOString(),
                      };
                    }
                    return {
                      ...a,
                      status: "completed" as const,
                      completedAt: new Date().toISOString(),
                    };
                  }),
                );
                break;
              }

              case "done":
                clearTimeout(timeoutId);
                setPhase("complete");
                setIsLoading(false);
                if (event.data.session_id) {
                  setSessionId(event.data.session_id as string);
                }
                setAgents((prev) =>
                  prev.map((a) => {
                    // Keep pre-marked completed agents; only pending → skipped
                    if (a.status === "pending") {
                      return { ...a, status: "skipped" as const };
                    }
                    return a;
                  }),
                );
                // After a decision-only turn, nudge user to continue
                if (sawDecision && !sawClarification && !sawPrd) {
                  setMessages((prev) => {
                    const without = prev.filter(
                      (m) => m.metadata?.kind !== "continue_prompt",
                    );
                    return [
                      ...without,
                      {
                        id: `continue-${Date.now()}`,
                        role: "assistant",
                        content: "下一步",
                        timestamp: new Date(),
                        metadata: { kind: "continue_prompt" },
                      },
                    ];
                  });
                }
                break;

              case "error":
                clearTimeout(timeoutId);
                setIsLoading(false);
                setPhase("idle");
                setMessages((prev) => [
                  ...prev,
                  {
                    id: `error-${Date.now()}`,
                    role: "system",
                    content: `⚠️ 发生错误: ${
                      typeof event.data === "string"
                        ? event.data
                        : event.data.message || JSON.stringify(event.data)
                    }`,
                    timestamp: new Date(),
                  },
                ]);
                break;
            }
          },
          {
            demoMode,
            skipClarify: false,
            messageHistory,
          },
        );
        if (timeoutId !== undefined) clearTimeout(timeoutId);
        setSessionId(newSessionId);
        setIsLoading(false);
      } catch (error) {
        if (timeoutId !== undefined) clearTimeout(timeoutId);
        setIsLoading(false);
        setMessages((prev) => [
          ...prev,
          {
            id: `error-${Date.now()}`,
            role: "system",
            content: `⚠️ ${error instanceof Error ? error.message : String(error)}`,
            timestamp: new Date(),
          },
        ]);
      }
    },
    [
      sessionId,
      messages,
      agents,
      awaitingClarification,
      clarifyResumePhase,
      demoMode,
      decisionDone,
    ],
  );

  useEffect(() => {
    sendMessageRef.current = handleSendMessage;
  }, [handleSendMessage]);

  const activeProjectName =
    historyStore?.projects.find((p) => p.id === historyStore.activeProjectId)
      ?.name || "默认项目";
  const activeChatTitle = historyStore
    ? getActiveConversation(historyStore)?.title || "新对话"
    : "新对话";

  return (
    <div className="flex h-screen overflow-hidden">
      {historyStore && (
        <HistorySidebar
          store={historyStore}
          collapsed={sidebarCollapsed}
          onToggleCollapsed={() => setSidebarCollapsed((v) => !v)}
          onNewChat={handleNewChat}
          onNewProject={handleNewProject}
          onSelectConversation={handleSelectConversation}
          onDeleteConversation={handleDeleteConversation}
          onDeleteProject={handleDeleteProject}
          onRenameProject={handleRenameProject}
        />
      )}

      <div className="flex min-w-0 flex-1 flex-col border-r border-border">
        <header className="flex items-center justify-between border-b border-border px-6 py-3">
          <div className="min-w-0">
            <div className="flex items-baseline gap-2">
              <h1 className="text-base font-semibold text-foreground">
                PM Copilot
              </h1>
              <span className="text-[11px] text-muted-foreground">
                AI 产品经理助手
              </span>
            </div>
            <p className="mt-0.5 truncate text-xs text-muted-foreground">
              {activeProjectName}
              <span className="mx-1 text-border">/</span>
              {activeChatTitle}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={demoMode}
                onChange={(e) => setDemoMode(e.target.checked)}
                className="rounded border-border"
              />
              演示模式
              <span className="text-[10px] opacity-70">（低成本）</span>
            </label>
            {rateLimitRemaining !== null && (
              <span className="text-[11px] text-muted-foreground">
                今日剩余 {rateLimitRemaining} 次
              </span>
            )}
            <div className="flex items-center gap-2">
              <span
                className={`inline-block h-2 w-2 rounded-full ${
                  phase === "idle"
                    ? "bg-agent-pending"
                    : phase === "complete"
                      ? "bg-agent-completed"
                      : "bg-agent-running animate-pulse-dot"
                }`}
              />
              <span className="text-xs text-muted-foreground">
                {awaitingClarification
                  ? "确认中"
                  : phase === "idle"
                    ? "就绪"
                    : phase === "complete"
                      ? "完成"
                      : "执行中..."}
              </span>
            </div>
          </div>
        </header>

        {memoryEmpty && (
          <div className="border-b border-amber-500/30 bg-amber-500/10 px-6 py-2 text-xs text-amber-100">
            知识库为空，本次分析未引用组织记忆。可在右侧上传历史文档后再试。
          </div>
        )}

        <ChatWindow
          messages={messages}
          isLoading={isLoading}
          onClarifySelect={handleSendMessage}
          onContinue={handleContinue}
        />

        <div className="border-t border-border p-4">
          {!awaitingClarification && (
            <div className="mb-3 flex flex-wrap gap-2">
              {QUICK_ACTIONS.map((action) => (
                <button
                  key={action.id}
                  onClick={() =>
                    handleSendMessage(`请帮我${action.label}`, action.phase)
                  }
                  disabled={isLoading}
                  className="flex items-center gap-1.5 rounded-lg border border-border bg-secondary px-3 py-1.5 text-xs text-secondary-foreground transition-colors hover:bg-accent disabled:opacity-50"
                >
                  <span>{action.icon}</span>
                  <span>{action.label}</span>
                </button>
              ))}
            </div>
          )}
          <InputBar
            onSend={handleSendMessage}
            disabled={isLoading}
            placeholder={
              awaitingClarification
                ? "也可以自己补充一句…"
                : "描述你的产品需求..."
            }
          />
        </div>
      </div>

      <div className="flex w-96 flex-col bg-card">
        <div className="border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold text-foreground">Agent 协作面板</h2>
          <p className="text-xs text-muted-foreground">实时查看各 Agent 执行状态</p>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          <AgentStatus agents={agents} />
        </div>

        <div className="border-t border-border p-4">
          <h3 className="mb-2 text-xs font-semibold text-muted-foreground">执行时间线</h3>
          <AgentTimeline agents={agents} />
        </div>

        <div className="border-t border-border p-4">
          <MemoryPanel citations={citations} memoryEmpty={memoryEmpty} />
        </div>
      </div>
    </div>
  );
}

function buildInitialAgents(
  phase: string,
  prior: AgentState[],
  hadDecision: boolean,
): AgentState[] {
  const priorByName = Object.fromEntries(prior.map((a) => [a.name, a]));
  const agents: AgentState[] = [
    { name: "orchestrator", displayName: "编排器", icon: "🧭", status: "pending" },
    { name: "org_memory", displayName: "组织记忆", icon: "🧠", status: "pending" },
    { name: "decision", displayName: "决策顾问", icon: "🎯", status: "pending" },
    { name: "prd_writer", displayName: "PRD 撰写", icon: "📝", status: "pending" },
    { name: "critic", displayName: "质量审查", icon: "🔍", status: "pending" },
    { name: "stress_test", displayName: "压力测试", icon: "⚡", status: "pending" },
    {
      name: "memory_writeback",
      displayName: "记忆回流",
      icon: "💾",
      status: "skipped",
      summary: "仅上传入库，不自动写入",
    },
  ];

  const markPriorCompleted = (name: AgentName, label = "此前已完成") => {
    const row = agents.find((a) => a.name === name);
    if (!row) return;
    row.status = "completed";
    row.completedAt =
      priorByName[name]?.completedAt || new Date().toISOString();
    row.summary = label;
  };

  // Downstream-only runs: keep upstream steps green instead of "skipped"
  if (phase === "prd_generation" || phase === "stress_test") {
    if (hadDecision || priorByName.decision?.status === "completed") {
      markPriorCompleted("decision");
    }
  }
  if (phase === "stress_test") {
    if (priorByName.prd_writer?.status === "completed") {
      markPriorCompleted("prd_writer");
    }
    if (priorByName.critic?.status === "completed") {
      markPriorCompleted("critic");
    }
  }

  return agents;
}

/** Build history blob matching backend format_clarify_step for next-turn parsing. */
function formatClarifyHistory(step: ClarifyStep): string {
  const payload = {
    mode: "clarify_step",
    step: step.step ?? 1,
    max_steps: step.max_steps ?? 3,
    id: step.id || `step_${step.step ?? 1}`,
    question: step.question,
    options: step.options || [],
    allow_custom: step.allow_custom !== false,
    hint: step.hint || "",
  };
  const lines = [
    "## 决策确认",
    "",
    `**确认 (${payload.step}/${payload.max_steps})**`,
    "",
    step.question,
    "",
    "```json",
    JSON.stringify(payload),
    "```",
  ];
  return lines.join("\n");
}

function formatDecisionOutput(decision: any): string {
  const emoji =
    decision.recommendation === "GO"
      ? "✅"
      : decision.recommendation === "PIVOT"
        ? "🔄"
        : "❌";
  let text = `## ${emoji} 决策建议: ${decision.recommendation}\n\n`;
  text += `**置信度**: ${(decision.confidence * 100).toFixed(0)}%\n\n`;
  text += `**分析理由**:\n${decision.reasoning}\n\n`;

  if (decision.risks?.length) {
    text += "**识别风险**:\n";
    decision.risks.forEach((r: string) => {
      text += `- ${r}\n`;
    });
    text += "\n";
  }

  if (decision.five_w_one_h) {
    text += "**5W1H 分析**:\n";
    const labels: Record<string, string> = {
      what: "做什么",
      why: "为什么",
      who: "给谁用",
      when: "何时",
      where: "在哪",
      how: "怎么做",
    };
    Object.entries(decision.five_w_one_h).forEach(([k, v]) => {
      if (v) text += `- **${labels[k] || k}**: ${v}\n`;
    });
  }

  return text;
}

function formatCriticOutput(critic: CriticFeedback): string {
  if (critic.review) return critic.review;
  let text = `## 质量审查\n\n**评分**: ${critic.score ?? "N/A"}/10\n\n`;
  text += `**结论**: ${critic.verdict || "N/A"}\n\n`;
  if (critic.summary) text += `**摘要**: ${critic.summary}\n\n`;
  if (critic.strengths?.length) {
    text += "**优点**:\n";
    critic.strengths.forEach((s) => {
      text += `- ${s}\n`;
    });
    text += "\n";
  }
  if (critic.improvements?.length) {
    text += "**改进建议**:\n";
    critic.improvements.forEach((s) => {
      text += `- ${s}\n`;
    });
  }
  return text;
}

function formatStressTestOutput(challenges: any[], summary?: any): string {
  let text = "## ⚡ 压力测试报告\n\n";
  if (summary) {
    if (summary.summary === "skipped_in_demo_mode") {
      return "## ⚡ 压力测试\n\n演示模式下已跳过压力测试以控制成本。关闭「演示模式」后可完整运行。\n";
    }
    text += `**综合评分**: ${summary.overall_score}/100\n\n`;
  }

  challenges.forEach((c) => {
    const severityEmoji: Record<string, string> = {
      low: "🟢",
      medium: "🟡",
      high: "🟠",
      critical: "🔴",
    };
    text += `### ${c.role}\n`;
    text += `${severityEmoji[c.severity] || "⚪"} 严重度: ${c.severity}\n`;
    text += `${c.challenge}\n`;
    if (c.suggestions?.length) {
      text += "**建议**:\n";
      c.suggestions.forEach((s: string) => {
        text += `- ${s}\n`;
      });
    }
    text += "\n";
  });

  return text;
}
