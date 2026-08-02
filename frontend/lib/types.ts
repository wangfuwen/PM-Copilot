/**
 * TypeScript type definitions for PM Copilot frontend.
 * Mirrors the backend Pydantic models for type safety.
 */

// ──────────────────────────────────────────────
// Agent Types
// ──────────────────────────────────────────────

export type AgentName =
  | "orchestrator"
  | "org_memory"
  | "decision"
  | "prd_writer"
  | "stress_test"
  | "memory_writeback"
  | "critic";

export type AgentStatus = "pending" | "running" | "completed" | "failed" | "skipped";

export type WorkflowPhase = "idle" | "decision" | "prd_generation" | "stress_test" | "review" | "complete";

export interface AgentState {
  name: AgentName;
  displayName: string;
  icon: string;
  status: AgentStatus;
  startedAt?: string;
  completedAt?: string;
  summary?: string;
  output?: AgentOutput;
}

export interface MemoryCitation {
  index?: number;
  doc_id?: string;
  chunk_id?: string;
  title?: string;
  doc_type?: string;
  score?: number;
  preview?: string;
}

export interface ClarifyOption {
  id: string;
  label: string;
}

/** Single progressive clarify step (Cursor-style). */
export interface ClarifyStep {
  mode?: string;
  step?: number;
  max_steps?: number;
  id?: string;
  question: string;
  options: ClarifyOption[];
  allow_custom?: boolean;
  hint?: string;
}

/** @deprecated Use ClarifyStep — kept for transitional typing */
export type ClarifyingQuestions = ClarifyStep;

export interface CriticFeedback {
  score?: number;
  verdict?: string;
  strengths?: string[];
  improvements?: string[];
  summary?: string;
  review?: string;
}

export interface AgentOutput {
  decision?: DecisionOutput;
  prd?: string;
  stressTest?: StressTestChallenge[];
  stressTestSummary?: StressTestSummary;
  citations?: MemoryCitation[];
  clarifying_questions?: ClarifyStep;
  awaiting_clarification?: boolean;
  critic?: CriticFeedback;
  memory_empty?: boolean;
  org_profile_summary?: {
    terminology?: Record<string, string>;
    lessons_count?: number;
    review_focus?: string[];
  };
  writeback_ids?: string[];
}

export interface MemoryChunk {
  chunk_id: string;
  doc_id: string;
  title: string;
  doc_type: string;
  section_title?: string;
  content: string;
  metadata?: Record<string, unknown>;
}

// ──────────────────────────────────────────────
// Decision Types
// ──────────────────────────────────────────────

export interface FiveWOneH {
  what?: string;
  why?: string;
  who?: string;
  when?: string;
  where?: string;
  how?: string;
}

export type Recommendation = "GO" | "PIVOT" | "KILL";

export interface DecisionOutput {
  five_w_one_h: FiveWOneH;
  recommendation: Recommendation;
  reasoning: string;
  risks: string[];
  confidence: number;
}

// ──────────────────────────────────────────────
// Stress Test Types
// ──────────────────────────────────────────────

export type Severity = "low" | "medium" | "high" | "critical";

export interface StressTestChallenge {
  role: string;
  challenge: string;
  severity: Severity;
  suggestions: string[];
}

export interface StressTestSummary {
  overall_score: number;
  summary: string;
}

// ──────────────────────────────────────────────
// Chat Types
// ──────────────────────────────────────────────

export interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  agentName?: AgentName;
  timestamp: Date;
  metadata?: Record<string, unknown>;
}

export interface ChatSession {
  id: string;
  messages: Message[];
  phase: WorkflowPhase;
  agents: AgentState[];
  createdAt: Date;
}

// ──────────────────────────────────────────────
// SSE Event Types
// ──────────────────────────────────────────────

export type SSEEventType =
  | "ping"
  | "agent_start"
  | "agent_output"
  | "agent_complete"
  | "done"
  | "error";

export interface SSEEvent {
  type: SSEEventType;
  data: {
    agent?: AgentName;
    session_id?: string;
    output?: AgentOutput;
    agents_executed?: AgentName[];
    rate_limit_remaining?: number;
    demo_mode?: boolean;
    message?: string;
    [key: string]: unknown;
  };
}

// ──────────────────────────────────────────────
// Memory Types
// ──────────────────────────────────────────────

export interface MemoryResult {
  content: string;
  metadata: Record<string, unknown>;
  score: number;
  doc_type: string;
  doc_id?: string;
  title?: string;
  chunk_id?: string;
}

export interface MemoryDoc {
  doc_id: string;
  title: string;
  doc_type: string;
  source?: string;
  chunk_count?: number;
  preview?: string;
}

export interface OrgProfile {
  document_style?: Record<string, unknown>;
  terminology?: {
    internal_terms?: Record<string, string>;
    mapping?: Record<string, string>;
  };
  review_focus?: { top_3_dimensions?: string[] };
  lessons_learned?: string[];
  success_patterns?: string[];
}

// ──────────────────────────────────────────────
// Quick Action Types
// ──────────────────────────────────────────────

export interface QuickAction {
  id: string;
  label: string;
  description: string;
  phase: WorkflowPhase | "auto";
  icon: string;
}
