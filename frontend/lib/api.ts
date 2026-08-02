/**
 * API client for PM Copilot backend.
 * Handles communication with the FastAPI backend,
 * including SSE streaming for real-time agent updates.
 */

import type { SSEEvent, MemoryResult, MemoryDoc, OrgProfile, MemoryChunk } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api";

export interface ChatOptions {
  demoMode?: boolean;
  skipClarify?: boolean;
  messageHistory?: { role: string; content: string }[];
  signal?: AbortSignal;
}

/**
 * Send a chat message and receive streaming SSE events.
 */
export async function sendChatMessage(
  message: string,
  sessionId: string | null,
  phase: string = "auto",
  onEvent: (event: SSEEvent) => void,
  options: ChatOptions = {},
): Promise<string> {
  const payload: Record<string, unknown> = {
    message,
    session_id: sessionId,
    phase,
    demo_mode: Boolean(options.demoMode),
    skip_clarify: Boolean(options.skipClarify),
  };
  if (options.messageHistory && options.messageHistory.length > 0) {
    payload.messages = options.messageHistory;
  }

  const response = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal: options.signal,
  });

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      // ignore
    }
    throw new Error(
      response.status === 429
        ? detail
        : `API error: ${detail}`,
    );
  }

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
        currentEventType = "agent_output";
      }
    }
  }

  return currentSessionId;
}

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

export async function deleteMemoryDoc(docId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/memory/docs/${docId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(`Memory delete error: ${response.status}`);
  }
}

export async function getOrgProfile(): Promise<{ profile: OrgProfile; path: string }> {
  const response = await fetch(`${API_BASE}/memory/profile`);
  if (!response.ok) {
    throw new Error(`Org profile error: ${response.status}`);
  }
  return response.json();
}

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

/** Fetch full chunk text for a citation. */
export async function getMemoryChunk(chunkId: string): Promise<MemoryChunk> {
  const response = await fetch(
    `${API_BASE}/memory/chunks/${encodeURIComponent(chunkId)}`,
  );
  if (!response.ok) {
    throw new Error(`Chunk fetch error: ${response.status}`);
  }
  return response.json();
}

export async function getAgentStatus(sessionId: string) {
  const response = await fetch(`${API_BASE}/agents/status?session_id=${sessionId}`);

  if (!response.ok) {
    throw new Error(`Agent status error: ${response.status}`);
  }

  return response.json();
}
