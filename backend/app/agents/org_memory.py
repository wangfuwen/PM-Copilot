"""
Org Memory Agent — 组织记忆管理。

Handles vector storage and retrieval of organizational knowledge:
- Historical PRDs and their outcomes
- Decision records and their rationale
- Lessons learned from stress tests
- Meeting notes and product insights
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.memory.vector_store import VectorStore, get_vector_store
from app.memory.org_profile import (
    load_org_profile,
    format_org_profile_for_prompt,
)
from app.prompts.org_memory import ORG_MEMORY_SUMMARIZE_PROMPT

logger = logging.getLogger(__name__)


class OrgMemoryAgent:
    """Org Memory Agent for retrieve + store against shared VectorStore."""

    def __init__(self, llm: BaseChatModel, vector_store: Optional[VectorStore] = None):
        self.llm = llm
        self.vector_store = vector_store or get_vector_store()

    async def retrieve_context(
        self,
        query: str,
        n_results: int = 5,
        doc_types: Optional[list[str]] = None,
    ) -> tuple[str, list[dict]]:
        """
        Retrieve relevant organizational memory.

        Returns:
            (formatted_context, citations)
        """
        results = self.vector_store.search(
            query=query,
            n_results=n_results,
            doc_types=doc_types,
        )
        if not results:
            return "", []

        citations: list[dict] = []
        context_parts: list[str] = []
        for i, r in enumerate(results, 1):
            title = r.get("title") or "Untitled"
            doc_type = r.get("doc_type", "unknown")
            score = r.get("score", 0)
            content = r.get("content", "")
            citations.append(
                {
                    "index": i,
                    "doc_id": r.get("doc_id", ""),
                    "chunk_id": r.get("chunk_id", ""),
                    "title": title,
                    "doc_type": doc_type,
                    "score": score,
                    "preview": content[:180],
                }
            )
            context_parts.append(
                f"[{i}] ({doc_type}) {title} (相关度: {score:.2f})\n{content}"
            )

        return "\n\n".join(context_parts), citations

    async def store_document(
        self,
        content: str,
        doc_type: str = "other",
        metadata: dict | None = None,
        *,
        summarize_if_long: bool = True,
    ) -> str:
        """Store a document, optionally summarizing long content first."""
        meta = dict(metadata or {})
        to_store = content

        if summarize_if_long and len(content) > 2000:
            messages = [
                SystemMessage(
                    content=ORG_MEMORY_SUMMARIZE_PROMPT.replace(
                        "{document_content}", content[:3000]
                    )
                ),
                HumanMessage(content="请按要求总结以上文档。"),
            ]
            try:
                response = await self.llm.ainvoke(messages)
                to_store = response.content
                meta["summarized"] = True
            except Exception as e:
                logger.warning("Summarize before store failed, storing truncated raw: %s", e)
                to_store = content[:3000]
                meta["summarized"] = False

        doc_id = self.vector_store.add_document(
            content=to_store,
            metadata=meta,
            doc_type=doc_type,
        )
        logger.info("OrgMemoryAgent: Stored document %s (type=%s)", doc_id, doc_type)
        return doc_id

    async def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        """LangGraph node: retrieve context + load Org Profile."""
        user_input = state.get("user_input", "") or ""
        phase = state.get("current_phase", "auto")

        logger.info("OrgMemoryAgent: Retrieving relevant context...")
        context, citations = await self.retrieve_context(user_input, n_results=5)

        # Extra history-oriented retrieval for stress / review paths
        history_context = ""
        history_citations: list[dict] = []
        if phase in ("stress_test", "prd_generation", "auto", "decision"):
            history_context, history_citations = await self.retrieve_context(
                user_input,
                n_results=3,
                doc_types=["stress_test", "meeting_note", "other"],
            )

        profile = load_org_profile()
        profile_text = format_org_profile_for_prompt(profile)

        if context:
            logger.info("OrgMemoryAgent: Found context (%s chars)", len(context))
        else:
            logger.info("OrgMemoryAgent: No relevant context found")

        # Merge citations (dedupe by chunk_id)
        all_citations = []
        seen = set()
        for c in citations + history_citations:
            key = c.get("chunk_id") or f"{c.get('doc_id')}-{c.get('index')}"
            if key in seen:
                continue
            seen.add(key)
            all_citations.append(c)

        return {
            **state,
            "org_memory_context": context,
            "org_history_context": history_context,
            "org_profile": profile,
            "org_profile_text": profile_text,
            "memory_citations": all_citations,
        }


async def write_back_results(state: dict[str, Any], llm: BaseChatModel) -> list[str]:
    """Persist decision / PRD / stress summary into org memory after a run."""
    agent = OrgMemoryAgent(llm=llm, vector_store=get_vector_store())
    stored_ids: list[str] = []
    user_input = (state.get("user_input") or "")[:80]

    decision = state.get("decision_output")
    if decision:
        content = json.dumps(decision, ensure_ascii=False, indent=2)
        doc_id = await agent.store_document(
            content=content,
            doc_type="decision",
            metadata={
                "title": f"决策-{decision.get('recommendation', 'N/A')}-{user_input}",
                "source": "workflow_writeback",
            },
            summarize_if_long=False,
        )
        stored_ids.append(doc_id)

    prd = state.get("prd_output")
    if prd:
        doc_id = await agent.store_document(
            content=prd,
            doc_type="prd",
            metadata={
                "title": f"PRD-{user_input or 'generated'}",
                "source": "workflow_writeback",
            },
            summarize_if_long=True,
        )
        stored_ids.append(doc_id)

    stress = state.get("stress_test_summary")
    if stress:
        challenges = state.get("stress_test_results") or []
        content = json.dumps(
            {"summary": stress, "challenges": challenges[:10]},
            ensure_ascii=False,
            indent=2,
        )
        doc_id = await agent.store_document(
            content=content,
            doc_type="stress_test",
            metadata={
                "title": f"压力测试-{user_input or 'run'}",
                "source": "workflow_writeback",
            },
            summarize_if_long=False,
        )
        stored_ids.append(doc_id)

    return stored_ids
