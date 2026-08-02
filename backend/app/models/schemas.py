"""
Pydantic data models for PM Copilot API.
Defines request/response schemas and internal data structures.
"""

from typing import Optional, Literal
from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
# Chat
# ──────────────────────────────────────────────
class ChatRequest(BaseModel):
    """User chat request."""
    message: str = Field(..., description="User message / requirement description")
    session_id: Optional[str] = Field(None, description="Conversation session ID, auto-generated if not provided")
    phase: Optional[Literal["decision", "prd_generation", "stress_test", "auto", "full_pipeline"]] = Field(
        "auto", description="Force a specific phase, or 'auto' to let orchestrator decide"
    )
    messages: Optional[list[dict]] = Field(
        None, description="Full conversation history for context (list of {role, content})"
    )
    demo_mode: bool = Field(
        default=False,
        description="Cheaper path: prefer mini models and optionally skip stress test",
    )
    skip_clarify: bool = Field(
        default=False,
        description="Skip clarifying questions and decide immediately",
    )


class ChatResponse(BaseModel):
    """Non-streaming chat response (fallback)."""
    session_id: str
    phase: str
    result: str
    agent_outputs: dict = Field(default_factory=dict)


# ──────────────────────────────────────────────
# Agent Status
# ──────────────────────────────────────────────
class AgentStatusItem(BaseModel):
    """Status of a single agent execution."""
    agent_name: str
    status: Literal["pending", "running", "completed", "failed", "skipped"]
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    summary: Optional[str] = None


class AgentStatusResponse(BaseModel):
    """Response for agent status query."""
    session_id: str
    current_phase: str
    agents: list[AgentStatusItem]


# ──────────────────────────────────────────────
# Memory
# ──────────────────────────────────────────────
DocType = Literal["prd", "decision", "stress_test", "meeting_note", "other"]


class MemorySearchRequest(BaseModel):
    """Request to search organizational memory."""
    query: str = Field(..., description="Search query")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of results to return")
    doc_type: Optional[DocType] = Field(None, description="Optional filter by document type")


class MemorySearchResult(BaseModel):
    """A single memory search result."""
    content: str
    metadata: dict = Field(default_factory=dict)
    score: float = Field(default=0.0, description="Relevance score")
    doc_type: str = Field(default="unknown")
    doc_id: str = Field(default="", description="Parent document ID")
    title: str = Field(default="Untitled")
    chunk_id: str = Field(default="")


class MemorySearchResponse(BaseModel):
    """Response for memory search."""
    results: list[MemorySearchResult]


class MemoryStoreRequest(BaseModel):
    """Request to store a document in organizational memory."""
    content: str = Field(..., description="Document content")
    doc_type: DocType = Field(default="other", description="Document type for categorization")
    metadata: dict = Field(default_factory=dict, description="Additional metadata (title, author, tags, etc.)")
    title: Optional[str] = Field(None, description="Document title")
    rebuild_profile: bool = Field(default=False, description="Rebuild Org Profile after store")


class MemoryStoreResponse(BaseModel):
    """Response for memory store."""
    doc_id: str
    status: str
    chunk_count: int = 0


class MemoryUploadRequest(BaseModel):
    """Upload markdown content into organizational memory."""
    content: str = Field(..., description="Markdown document content")
    title: str = Field(..., description="Document title")
    doc_type: DocType = Field(default="prd", description="Document type")
    rebuild_profile: bool = Field(
        default=True,
        description="Whether to rebuild Org Profile after upload",
    )


class MemoryUploadResponse(BaseModel):
    """Response after markdown upload."""
    doc_id: str
    status: str
    chunk_count: int = 0
    profile_rebuilt: bool = False


class MemoryDocItem(BaseModel):
    """Listed parent document in the knowledge base."""
    doc_id: str
    title: str
    doc_type: str
    source: str = ""
    chunk_count: int = 0
    preview: str = ""


class MemoryDocsResponse(BaseModel):
    """Knowledge base document list."""
    documents: list[MemoryDocItem]
    stats: dict = Field(default_factory=dict)


class OrgProfileResponse(BaseModel):
    """Org Profile payload."""
    profile: dict = Field(default_factory=dict)
    path: str = ""



# ──────────────────────────────────────────────
# Internal Agent Output Models
# ──────────────────────────────────────────────
class DecisionOutput(BaseModel):
    """Structured output from the Decision Agent."""
    five_w_one_h: dict = Field(default_factory=dict, description="5W1H analysis")
    recommendation: Literal["GO", "PIVOT", "KILL"] = Field(..., description="Decision recommendation")
    reasoning: str = Field(..., description="Detailed reasoning")
    risks: list[str] = Field(default_factory=list, description="Identified risks")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence level")


class StressTestChallenge(BaseModel):
    """A single challenge from a stress test role."""
    role: str = Field(..., description="Role name (e.g., '老板', '开发')")
    challenge: str = Field(..., description="Challenge description")
    severity: Literal["low", "medium", "high", "critical"] = Field(default="medium")
    suggestions: list[str] = Field(default_factory=list)


class StressTestOutput(BaseModel):
    """Aggregated stress test results."""
    challenges: list[StressTestChallenge]
    overall_score: float = Field(default=0.0, ge=0.0, le=100.0, description="Overall PRD health score")
    summary: str = Field(default="", description="Executive summary of findings")
