"use client";

import { useState, useCallback } from "react";
import { ChatWindow } from "@/components/chat/ChatWindow";
import { InputBar } from "@/components/chat/InputBar";
import { AgentStatus } from "@/components/agents/AgentStatus";
import { AgentTimeline } from "@/components/agents/AgentTimeline";
import { MemoryPanel } from "@/components/memory/MemoryPanel";
import type { Message, AgentState, WorkflowPhase, SSEEvent, MemoryCitation } from "@/lib/types";

// Quick action presets
const QUICK_ACTIONS = [
  { id: "analyze", label: "分析需求", description: "5W1H 分析 + 决策建议", phase: "decision" as const, icon: "🔍" },
  { id: "prd", label: "生成 PRD", description: "结构化产品需求文档", phase: "prd_generation" as const, icon: "📄" },
  { id: "stress", label: "压力测试", description: "5 角色红队挑战", phase: "stress_test" as const, icon: "⚡" },
];

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content: "你好！我是 PM Copilot，你的 AI 产品经理助手。\n\n我可以帮你：\n- 🔍 **分析需求**：用 5W1H 框架评估需求质量，给出 GO/PIVOT/KILL 建议\n- 📄 **生成 PRD**：输出结构化的产品需求文档\n- ⚡ **压力测试**：从 5 个关键角色视角挑战你的方案\n\n试试输入你的产品需求，或点击下方的快捷操作按钮。",
      timestamp: new Date(),
    },
  ]);
  const [agents, setAgents] = useState<AgentState[]>([]);
  const [phase, setPhase] = useState<WorkflowPhase>("idle");
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [citations, setCitations] = useState<MemoryCitation[]>([]);

  const handleSendMessage = useCallback(async (content: string, forcedPhase?: string) => {
    // Add user message
    const userMsg: Message = {
      id: `user-${Date.now()}`,
      role: "user",
      content,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    // Initialize agent states
    const initialAgents: AgentState[] = [
      { name: "orchestrator", displayName: "编排器", icon: "🧭", status: "pending" },
      { name: "org_memory", displayName: "组织记忆", icon: "🧠", status: "pending" },
      { name: "decision", displayName: "决策顾问", icon: "🎯", status: "pending" },
      { name: "prd_writer", displayName: "PRD 撰写", icon: "📝", status: "pending" },
      { name: "stress_test", displayName: "压力测试", icon: "⚡", status: "pending" },
      { name: "memory_writeback", displayName: "记忆回流", icon: "💾", status: "pending" },
    ];
    setAgents(initialAgents);
    setCitations([]);

    // Declared outside try so catch/finally can clear it (const inside try is block-scoped)
    let timeoutId: ReturnType<typeof setTimeout> | undefined;

    try {
      const { sendChatMessage } = await import("@/lib/api");

      // Build conversation history for context (exclude welcome/system messages)
      const messageHistory = messages
        .filter((m) => m.role === "user" || (m.role === "assistant" && !m.id.startsWith("welcome")))
        .map((m) => ({ role: m.role, content: m.content }));

      // Frontend-side timeout: if no SSE events arrive within 120s, clear loading
      timeoutId = setTimeout(() => {
        setIsLoading(false);
        setPhase("idle");
        setMessages((prev) => [
          ...prev,
          {
            id: `timeout-${Date.now()}`,
            role: "system",
            content: "️ 请求超时：LLM 响应时间过长，请检查网络或 API Key 配置。后端日志可能有更多错误信息。",
            timestamp: new Date(),
          },
        ]);
      }, 120000); // 2 minutes

      const newSessionId = await sendChatMessage(
        content,
        sessionId,
        forcedPhase || "auto",
        (event: SSEEvent) => {
          // Reset timeout on any event received
          clearTimeout(timeoutId);

          switch (event.type) {
            case "ping":
              // Connection alive, workflow starting
              break;

            case "agent_start":
              setAgents((prev) =>
                prev.map((a) =>
                  a.name === event.data.agent
                    ? { ...a, status: "running" as const, startedAt: new Date().toISOString() }
                    : a,
                ),
              );
              setPhase((prev) => (prev === "idle" ? "decision" : prev));
              break;

            case "agent_output":
              if (event.data.output) {
                const output = event.data.output as NonNullable<SSEEvent["data"]["output"]> & {
                  stress_test?: unknown;
                  stress_test_summary?: unknown;
                };
                if (output.citations && output.citations.length > 0) {
                  setCitations(output.citations);
                  const citeMsg: Message = {
                    id: `citations-${Date.now()}`,
                    role: "system",
                    content: formatCitations(output.citations),
                    agentName: "org_memory",
                    timestamp: new Date(),
                  };
                  setMessages((prev) => [...prev, citeMsg]);
                }
                if (output.decision) {
                  const decisionMsg: Message = {
                    id: `decision-${Date.now()}`,
                    role: "assistant",
                    content: formatDecisionOutput(output.decision),
                    agentName: "decision",
                    timestamp: new Date(),
                  };
                  setMessages((prev) => [...prev, decisionMsg]);
                }
                if (output.prd) {
                  const prdMsg: Message = {
                    id: `prd-${Date.now()}`,
                    role: "assistant",
                    content: output.prd,
                    agentName: "prd_writer",
                    timestamp: new Date(),
                  };
                  setMessages((prev) => [...prev, prdMsg]);
                }
                // Backend sends snake_case; types also allow camelCase
                const stressTest = output.stressTest ?? output.stress_test;
                const stressTestSummary =
                  output.stressTestSummary ?? output.stress_test_summary;
                if (stressTest) {
                  const stMsg: Message = {
                    id: `stress-${Date.now()}`,
                    role: "assistant",
                    content: formatStressTestOutput(stressTest as any[], stressTestSummary),
                    agentName: "stress_test",
                    timestamp: new Date(),
                  };
                  setMessages((prev) => [...prev, stMsg]);
                }
              }
              break;

            case "agent_complete":
              setAgents((prev) =>
                prev.map((a) =>
                  a.name === event.data.agent
                    ? { ...a, status: "completed" as const, completedAt: new Date().toISOString() }
                    : a,
                ),
              );
              break;

            case "done":
              clearTimeout(timeoutId);
              setPhase("complete");
              setIsLoading(false);
              if (event.data.session_id) {
                setSessionId(event.data.session_id as string);
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
                      : (event.data as { message?: string }).message || JSON.stringify(event.data)
                  }`,
                  timestamp: new Date(),
                },
              ]);
              break;
          }
        },
        undefined,  // signal
        messageHistory,
      );
      if (timeoutId !== undefined) clearTimeout(timeoutId);
      setSessionId(newSessionId);
      // Safety net: ensure loading is cleared even if SSE stream ends without a "done" event
      setIsLoading(false);
    } catch (error) {
      if (timeoutId !== undefined) clearTimeout(timeoutId);
      setIsLoading(false);
      setMessages((prev) => [
        ...prev,
        {
          id: `error-${Date.now()}`,
          role: "system",
          content: `⚠️ 连接失败，请检查后端服务是否启动: ${error}`,
          timestamp: new Date(),
        },
      ]);
    }
  }, [sessionId, messages]);

  return (
    <div className="flex h-screen">
      {/* Left: Chat area */}
      <div className="flex flex-1 flex-col border-r border-border">
        {/* Header */}
        <header className="flex items-center justify-between border-b border-border px-6 py-4">
          <div>
            <h1 className="text-xl font-bold text-foreground">PM Copilot</h1>
            <p className="text-sm text-muted-foreground">AI 产品经理的决策与质量保障助手</p>
          </div>
          <div className="flex items-center gap-2">
            <span className={`inline-block h-2 w-2 rounded-full ${phase === "idle" ? "bg-agent-pending" : phase === "complete" ? "bg-agent-completed" : "bg-agent-running animate-pulse-dot"}`} />
            <span className="text-xs text-muted-foreground">
              {phase === "idle" ? "就绪" : phase === "complete" ? "完成" : "执行中..."}
            </span>
          </div>
        </header>

        {/* Messages */}
        <ChatWindow messages={messages} isLoading={isLoading} />

        {/* Quick Actions + Input */}
        <div className="border-t border-border p-4">
          <div className="mb-3 flex gap-2">
            {QUICK_ACTIONS.map((action) => (
              <button
                key={action.id}
                onClick={() => handleSendMessage(`请帮我${action.label}`, action.phase)}
                disabled={isLoading}
                className="flex items-center gap-1.5 rounded-lg border border-border bg-secondary px-3 py-1.5 text-xs text-secondary-foreground transition-colors hover:bg-accent disabled:opacity-50"
              >
                <span>{action.icon}</span>
                <span>{action.label}</span>
              </button>
            ))}
          </div>
          <InputBar onSend={handleSendMessage} disabled={isLoading} />
        </div>
      </div>

      {/* Right: Agent + Memory panel */}
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
          <MemoryPanel citations={citations} />
        </div>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────
// Helper formatters
// ──────────────────────────────────────────────

function formatCitations(citations: MemoryCitation[]): string {
  let text = "## 🧠 组织记忆检索\n\n";
  citations.slice(0, 5).forEach((c, i) => {
    const score =
      typeof c.score === "number" ? ` · 相关度 ${(c.score * 100).toFixed(0)}%` : "";
    text += `${i + 1}. **${c.title || "Untitled"}** (${c.doc_type || "doc"}${score})\n`;
    if (c.preview) text += `   ${c.preview}\n`;
  });
  return text;
}

function formatDecisionOutput(decision: any): string {
  const emoji = decision.recommendation === "GO" ? "✅" : decision.recommendation === "PIVOT" ? "🔄" : "❌";
  let text = `## ${emoji} 决策建议: ${decision.recommendation}\n\n`;
  text += `**置信度**: ${(decision.confidence * 100).toFixed(0)}%\n\n`;
  text += `**分析理由**:\n${decision.reasoning}\n\n`;

  if (decision.risks?.length) {
    text += "**识别风险**:\n";
    decision.risks.forEach((r: string) => { text += `- ${r}\n`; });
    text += "\n";
  }

  if (decision.five_w_one_h) {
    text += "**5W1H 分析**:\n";
    const labels: Record<string, string> = { what: "做什么", why: "为什么", who: "给谁用", when: "何时", where: "在哪", how: "怎么做" };
    Object.entries(decision.five_w_one_h).forEach(([k, v]) => {
      if (v) text += `- **${labels[k] || k}**: ${v}\n`;
    });
  }

  return text;
}

function formatStressTestOutput(challenges: any[], summary?: any): string {
  let text = "## ⚡ 压力测试报告\n\n";
  if (summary) {
    text += `**综合评分**: ${summary.overall_score}/100\n\n`;
  }

  challenges.forEach((c) => {
    const severityEmoji: Record<string, string> = { low: "🟢", medium: "🟡", high: "🟠", critical: "🔴" };
    text += `### ${c.role}\n`;
    text += `${severityEmoji[c.severity] || "⚪"} 严重度: ${c.severity}\n`;
    text += `${c.challenge}\n`;
    if (c.suggestions?.length) {
      text += "**建议**:\n";
      c.suggestions.forEach((s: string) => { text += `- ${s}\n`; });
    }
    text += "\n";
  });

  return text;
}
