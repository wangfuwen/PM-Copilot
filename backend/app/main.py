"""
PM Copilot — FastAPI application entry point.
Provides REST API endpoints for chat, agent status, and memory operations.
"""

import uuid
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from app.config import settings
from app.models.schemas import (
    ChatRequest,
    AgentStatusResponse,
    MemorySearchRequest,
    MemorySearchResponse,
    MemorySearchResult,
    MemoryStoreRequest,
    MemoryStoreResponse,
    MemoryUploadRequest,
    MemoryUploadResponse,
    MemoryDocsResponse,
    MemoryDocItem,
    OrgProfileResponse,
)
from app.graph.workflow import build_workflow, run_workflow_streaming
from app.memory.vector_store import VectorStore, set_vector_store
from app.memory.org_profile import load_org_profile, rebuild_org_profile, profile_path
from app.rate_limit import DailyRateLimiter
from langchain_core.messages import HumanMessage, AIMessage

logger = logging.getLogger(__name__)
chat_limiter = DailyRateLimiter(settings.rate_limit_per_ip_per_day)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: startup & shutdown."""
    logger.info("Initializing PM Copilot...")

    if not settings.openai_api_key:
        logger.error("❌ OPENAI_API_KEY is not set! Please add it to your .env file.")
        raise RuntimeError("OPENAI_API_KEY is required. Please set it in backend/.env")
    logger.info("✅ OpenAI API key configured")

    if settings.anthropic_api_key:
        logger.info("✅ Anthropic API key configured")
    else:
        logger.warning(
            "⚠️  ANTHROPIC_API_KEY not set — Anthropic models disabled, using OpenAI for all agents"
        )

    model_summary = settings.get_agent_model_summary()
    for agent, model in model_summary.items():
        logger.info("  📌 %s: %s", agent, model)

    vector_store = VectorStore()
    set_vector_store(vector_store)
    app.state.vector_store = vector_store
    app.state.workflow = build_workflow()
    # Small bounded cache for phase-to-phase continuity. The browser also sends
    # the latest structured artifacts so refreshes and backend restarts recover.
    app.state.session_contexts = {}
    logger.info("✅ PM Copilot ready. Listening on http://%s:%s", settings.host, settings.port)
    yield
    logger.info("Shutting down PM Copilot...")


app = FastAPI(
    title="PM Copilot",
    description="AI Product Manager Copilot — Multi-Agent decision & quality assurance assistant",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────
# Chat endpoint (SSE streaming)
# ──────────────────────────────────────────────
@app.post("/api/chat", response_class=EventSourceResponse)
async def chat(request: ChatRequest, http_request: Request):
    """
    Main chat endpoint. Accepts user message, runs the multi-agent workflow,
    and streams results back via Server-Sent Events.
    """
    client_ip = http_request.client.host if http_request.client else "unknown"
    allowed, remaining, limit = chat_limiter.check(client_ip)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"今日试用次数已达上限（{limit} 次/IP）。请明天再试，或本地部署运行。",
        )

    session_id = request.session_id or str(uuid.uuid4())

    session_contexts: dict[str, dict] = app.state.session_contexts
    resume_context = dict(session_contexts.get(session_id) or {})
    if request.workflow_context:
        resume_context.update(request.workflow_context.model_dump(exclude_none=True))
    resume_context.setdefault("original_requirement", request.message)
    if request.phase == "stress_test" and not resume_context.get("prd_output"):
        if len(request.message.strip()) >= 100:
            resume_context["prd_output"] = request.message

    session_contexts[session_id] = resume_context
    while len(session_contexts) > 200:
        session_contexts.pop(next(iter(session_contexts)))

    message_history = None
    if request.messages:
        message_history = []
        for msg in request.messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                message_history.append(HumanMessage(content=content))
            elif role == "assistant":
                message_history.append(AIMessage(content=content))

    async def event_generator():
        yield {
            "event": "ping",
            "data": json.dumps(
                {
                    "session_id": session_id,
                    "status": "connected",
                    "rate_limit_remaining": remaining,
                    "demo_mode": bool(request.demo_mode or settings.demo_mode),
                },
                ensure_ascii=False,
            ),
        }
        logger.info(
            "Chat request received: message='%s...', phase=%s, session=%s demo=%s",
            request.message[:50],
            request.phase,
            session_id,
            request.demo_mode,
        )

        try:
            async for event in run_workflow_streaming(
                workflow=app.state.workflow,
                user_message=request.message,
                session_id=session_id,
                phase=request.phase,
                message_history=message_history,
                demo_mode=bool(request.demo_mode or settings.demo_mode),
                skip_clarify=bool(request.skip_clarify),
                resume_context=resume_context,
            ):
                if event["type"] == "agent_output" and isinstance(event.get("data"), dict):
                    output = event["data"].get("output") or {}
                    if output.get("decision"):
                        resume_context["decision_output"] = output["decision"]
                    if output.get("prd"):
                        resume_context["prd_output"] = output["prd"]
                        resume_context["accepted_issues"] = []
                    session_contexts[session_id] = dict(resume_context)
                raw = event["data"]
                data = (
                    raw
                    if isinstance(raw, str)
                    else json.dumps(raw, ensure_ascii=False, default=str)
                )
                yield {"event": event["type"], "data": data}
        except Exception as e:
            logger.exception("Workflow error")
            yield {
                "event": "error",
                "data": json.dumps({"message": str(e)}, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())


@app.get("/api/agents/status", response_model=AgentStatusResponse)
async def get_agent_status(session_id: str):
    """Query the execution status of all agents for a given session."""
    # TODO: integrate with LangGraph checkpoint to retrieve real status
    return AgentStatusResponse(
        session_id=session_id,
        agents=[],
        current_phase="idle",
    )


# ──────────────────────────────────────────────
# Memory endpoints
# ──────────────────────────────────────────────
@app.post("/api/memory/search", response_model=MemorySearchResponse)
async def search_memory(request: MemorySearchRequest):
    """Search organizational memory for relevant context."""
    vs: VectorStore = app.state.vector_store
    results = vs.search(
        query=request.query,
        n_results=request.top_k,
        doc_type=request.doc_type,
    )
    return MemorySearchResponse(
        results=[
            MemorySearchResult(
                content=r.get("content", ""),
                metadata=r.get("metadata") or {},
                score=r.get("score", 0.0),
                doc_type=r.get("doc_type", "unknown"),
                doc_id=r.get("doc_id", ""),
                title=r.get("title", "Untitled"),
                chunk_id=r.get("chunk_id", ""),
            )
            for r in results
        ]
    )


@app.post("/api/memory/store", response_model=MemoryStoreResponse)
async def store_memory(request: MemoryStoreRequest):
    """Store a new document into organizational memory (chunked)."""
    vs: VectorStore = app.state.vector_store
    meta = dict(request.metadata or {})
    if request.title:
        meta["title"] = request.title
    if "title" not in meta:
        meta["title"] = f"{request.doc_type}-{uuid.uuid4().hex[:8]}"

    before = vs.collection.count()
    doc_id = vs.add_document(
        content=request.content,
        metadata=meta,
        doc_type=request.doc_type,
    )
    chunk_count = max(0, vs.collection.count() - before)

    if request.rebuild_profile:
        samples = vs.get_sample_texts()
        await rebuild_org_profile(samples)

    return MemoryStoreResponse(doc_id=doc_id, status="stored", chunk_count=chunk_count)


@app.post("/api/memory/upload", response_model=MemoryUploadResponse)
async def upload_memory(request: MemoryUploadRequest):
    """Upload a Markdown document into the knowledge base."""
    if not request.content.strip():
        raise HTTPException(status_code=400, detail="content is empty")

    vs: VectorStore = app.state.vector_store
    before = vs.collection.count()
    doc_id = vs.add_document(
        content=request.content,
        metadata={"title": request.title, "source": request.title},
        doc_type=request.doc_type,
    )
    chunk_count = max(0, vs.collection.count() - before)

    profile_rebuilt = False
    if request.rebuild_profile:
        samples = vs.get_sample_texts()
        await rebuild_org_profile(samples)
        profile_rebuilt = True

    return MemoryUploadResponse(
        doc_id=doc_id,
        status="uploaded",
        chunk_count=chunk_count,
        profile_rebuilt=profile_rebuilt,
    )


@app.get("/api/memory/docs", response_model=MemoryDocsResponse)
async def list_memory_docs():
    """List parent documents in the knowledge base."""
    vs: VectorStore = app.state.vector_store
    docs = vs.list_documents()
    return MemoryDocsResponse(
        documents=[MemoryDocItem(**d) for d in docs],
        stats=vs.get_stats(),
    )


@app.delete("/api/memory/docs/{doc_id}")
async def delete_memory_doc(doc_id: str):
    """Delete a document and all its chunks."""
    vs: VectorStore = app.state.vector_store
    ok = vs.delete_document(doc_id)
    if not ok:
        raise HTTPException(status_code=404, detail="document not found or delete failed")
    return {"doc_id": doc_id, "status": "deleted"}


@app.get("/api/memory/profile", response_model=OrgProfileResponse)
async def get_org_profile():
    """Get the current Org Profile."""
    return OrgProfileResponse(profile=load_org_profile(), path=str(profile_path()))


@app.post("/api/memory/profile/rebuild", response_model=OrgProfileResponse)
async def rebuild_profile():
    """Rebuild Org Profile from documents currently in the knowledge base."""
    vs: VectorStore = app.state.vector_store
    samples = vs.get_sample_texts()
    if not samples:
        raise HTTPException(status_code=400, detail="knowledge base is empty")
    profile = await rebuild_org_profile(samples)
    return OrgProfileResponse(profile=profile, path=str(profile_path()))


@app.get("/api/memory/stats")
async def memory_stats():
    """Vector store statistics."""
    vs: VectorStore = app.state.vector_store
    return vs.get_stats()


@app.get("/api/memory/chunks/{chunk_id:path}")
async def get_memory_chunk(chunk_id: str):
    """Get full chunk content for clickable citations."""
    vs: VectorStore = app.state.vector_store
    chunk = vs.get_chunk(chunk_id)
    if not chunk:
        raise HTTPException(status_code=404, detail="chunk not found")
    return chunk


@app.get("/api/health")
async def health():
    """Lightweight health check for hosting platforms."""
    vs: VectorStore = app.state.vector_store
    stats = vs.get_stats()
    return {
        "status": "ok",
        "demo_mode": settings.demo_mode,
        "document_count": stats.get("document_count", 0),
        "rate_limit_per_ip_per_day": settings.rate_limit_per_ip_per_day,
    }
