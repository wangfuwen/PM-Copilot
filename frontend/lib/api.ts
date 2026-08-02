/**
 * API client for PM Copilot backend.
 * Handles communication with the FastAPI backend,
 * including SSE streaming for real-time agent updates.
 */

import type { SSEEvent, MemoryResult, MemoryDoc, OrgProfile } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api";

// ──────────────────────────────────────────────
// Chat API (SSE Streaming)
// ──────────────────────────────────────────────

/**
 * Send a chat message and receive streaming SSE events.
 *
 * @param message - User message to send
 * @param sessionId - Session ID (or null for new session)
 * @param phase - Forced phase or "auto"
 * @param onEvent - Callback for each SSE event
 * @param signal - AbortSignal for cancellation
 */
export async function sendChatMessage(
  message: string,
  sessionId: string | null,
  phase: string = "auto",
  onEvent: (event: SSEEvent) => void,
  signal?: AbortSignal,
  messageHistory?: { role: string; content: string }[],
): Promise<string> {
  const payload: Record<string, unknown> = {
    message,
    session_id: sessionId,
    phase,
  };
  // Include full conversation history for context
  if (messageHistory && messageHistory.length > 0) {
    payload.messages = messageHistory;
  }

  const response = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }

  // Parse SSE stream
  const reader = response.body?.getReader();
  const decoder = new TextDecoder();
  let currentSessionId = sessionId || "";

  if (!reader) throw new Error("No response body");

  let buffer = "";
  let currentEventType = "agent_output";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("event:")) {
        currentEventType = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        const dataStr = line.slice(5).trim();
        if (dataStr) {
          try {
            const data = JSON.parse(dataStr);
            if (data.session_id) currentSessionId = data.session_id;
            onEvent({
              type: currentEventType as SSEEvent["type"],
              data,
            });
          } catch {
            // Skip malformed data lines
          }
        }
        // Reset event type after processing data
        currentEventType = "agent_output";
      }
      // Empty lines are SSE event separators — no action needed
    }
  }

  return currentSessionId;
}

// ──────────────────────────────────────────────
// Memory API
// ──────────────────────────────────────────────

/**
 * Search organizational memory.
 */
export async function searchMemory(
  query: string,
  topK: number = 5,
): Promise<MemoryResult[]> {
  const response = await fetch(`${API_BASE}/memory/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k: topK }),
  });

  if (!response.ok) {
    throw new Error(`Memory search error: ${response.status}`);
  }

  const data = await response.json();
  return data.results;
}

/**
 * Store a document in organizational memory.
 */
export async function storeMemory(
  content: string,
  docType: string = "other",
  metadata: Record<string, unknown> = {},
): Promise<{ doc_id: string; status: string }> {
  const response = await fetch(`${API_BASE}/memory/store`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, doc_type: docType, metadata }),
  });

  if (!response.ok) {
    throw new Error(`Memory store error: ${response.status}`);
  }

  return response.json();
}

/**
 * Upload a Markdown document into the knowledge base.
 */
export async function uploadMemoryDoc(
  content: string,
  title: string,
  docType: string = "prd",
  rebuildProfile: boolean = true,
): Promise<{ doc_id: string; status: string; chunk_count: number; profile_rebuilt: boolean }> {
  const response = await fetch(`${API_BASE}/memory/upload`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      content,
      title,
      doc_type: docType,
      rebuild_profile: rebuildProfile,
    }),
  });

  if (!response.ok) {
    throw new Error(`Memory upload error: ${response.status}`);
  }

  return response.json();
}

/**
 * List knowledge base documents.
 */
export async function listMemoryDocs(): Promise<{
  documents: MemoryDoc[];
  stats: Record<string, unknown>;
}> {
  const response = await fetch(`${API_BASE}/memory/docs`);
  if (!response.ok) {
    throw new Error(`Memory docs error: ${response.status}`);
  }
  return response.json();
}

/**
 * Delete a knowledge base document.
 */
export async function deleteMemoryDoc(docId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/memory/docs/${docId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(`Memory delete error: ${response.status}`);
  }
}

/**
 * Get Org Profile.
 */
export async function getOrgProfile(): Promise<{ profile: OrgProfile; path: string }> {
  const response = await fetch(`${API_BASE}/memory/profile`);
  if (!response.ok) {
    throw new Error(`Org profile error: ${response.status}`);
  }
  return response.json();
}

/**
 * Rebuild Org Profile from current knowledge base.
 */
export async function rebuildOrgProfile(): Promise<{ profile: OrgProfile; path: string }> {
  const response = await fetch(`${API_BASE}/memory/profile/rebuild`, {
    method: "POST",
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Org profile rebuild error: ${response.status} ${detail}`);
  }
  return response.json();
}

// ──────────────────────────────────────────────
// Agent Status API
// ──────────────────────────────────────────────

/**
 * Get agent execution status for a session.
 */
export async function getAgentStatus(sessionId: string) {
  const response = await fetch(`${API_BASE}/agents/status?session_id=${sessionId}`);

  if (!response.ok) {
    throw new Error(`Agent status error: ${response.status}`);
  }

  return response.json();
}
