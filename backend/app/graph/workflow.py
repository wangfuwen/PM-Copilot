"""
LangGraph Workflow — 核心 Multi-Agent 编排逻辑。

Orchestrator → Org Memory → (Decision → PRD → Stress | PRD → Stress | Stress) → Writeback → END
"""

from __future__ import annotations

import logging
from typing import Any, Optional, AsyncIterator

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from typing_extensions import TypedDict

from app.config import settings

logger = logging.getLogger(__name__)


class AgentState(TypedDict, total=False):
    """Shared state flowing through the LangGraph workflow."""

    messages: list[BaseMessage]
    current_phase: str
    decision_output: Optional[dict]
    prd_output: Optional[str]
    stress_test_results: Optional[list]
    stress_test_summary: Optional[dict]
    critic_feedback: Optional[dict]
    org_memory_context: Optional[str]
    org_history_context: Optional[str]
    org_profile: Optional[dict]
    org_profile_text: Optional[str]
    memory_citations: Optional[list]
    memory_writeback_ids: Optional[list]
    next_agent: Optional[str]
    user_input: Optional[str]


def get_llm(agent_name: str = None):
    """Get the appropriate LLM for a given agent."""
    return settings.get_llm(agent_name=agent_name)


async def orchestrator_node(state: AgentState) -> dict:
    from app.agents.orchestrator import OrchestratorAgent

    try:
        llm = get_llm("orchestrator")
        agent = OrchestratorAgent(llm=llm)
        result = await agent(state)
        logger.info(
            "orchestrator_node: next_agent=%s, phase=%s",
            result.get("next_agent"),
            result.get("current_phase"),
        )
        return result
    except Exception as e:
        logger.error("orchestrator_node failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise


async def org_memory_node(state: AgentState) -> dict:
    from app.agents.org_memory import OrgMemoryAgent
    from app.memory.vector_store import get_vector_store

    try:
        llm = get_llm("org_memory")
        agent = OrgMemoryAgent(llm=llm, vector_store=get_vector_store())
        result = await agent(state)
        logger.info(
            "org_memory_node: context_found=%s citations=%s",
            bool(result.get("org_memory_context")),
            len(result.get("memory_citations") or []),
        )
        return result
    except Exception as e:
        logger.error("org_memory_node failed: %s: %s", type(e).__name__, e, exc_info=True)
        return {
            **state,
            "org_memory_context": "",
            "org_history_context": "",
            "org_profile_text": "",
            "memory_citations": [],
        }


async def decision_node(state: AgentState) -> dict:
    from app.agents.decision import DecisionAgent

    llm = get_llm("decision")
    agent = DecisionAgent(llm=llm)
    result = await agent(state)
    logger.info(
        "decision_node: recommendation=%s",
        (result.get("decision_output") or {}).get("recommendation"),
    )

    decision = result.get("decision_output", {})
    summary = f"决策建议: {decision.get('recommendation', 'N/A')} - {decision.get('reasoning', '')[:200]}"
    messages = list(state.get("messages", []))
    messages.append(AIMessage(content=summary, name="decision_agent"))
    return {**result, "messages": messages}


async def prd_writer_node(state: AgentState) -> dict:
    from app.agents.prd_writer import PRDWriterAgent

    llm = get_llm("prd_writer")
    agent = PRDWriterAgent(llm=llm)
    result = await agent(state)
    logger.info("prd_writer_node: generated %s chars", len(result.get("prd_output") or ""))

    prd = result.get("prd_output", "")
    messages = list(state.get("messages", []))
    messages.append(AIMessage(content=f"PRD 已生成 ({len(prd)} 字)", name="prd_writer_agent"))
    return {**result, "messages": messages}


async def stress_test_node(state: AgentState) -> dict:
    from app.agents.stress_test import StressTestAgent

    llm = get_llm("stress_test")
    agent = StressTestAgent(llm=llm)
    result = await agent(state)

    summary = result.get("stress_test_summary", {}) or {}
    messages = list(state.get("messages", []))
    score = summary.get("overall_score", 0)
    messages.append(
        AIMessage(content=f"压力测试完成，综合评分: {score}/100", name="stress_test_agent")
    )
    return {**result, "messages": messages}


async def memory_writeback_node(state: AgentState) -> dict:
    """Persist pipeline outputs into org memory for future retrieval."""
    from app.agents.org_memory import write_back_results

    try:
        llm = get_llm("org_memory")
        ids = await write_back_results(state, llm)
        logger.info("memory_writeback_node: stored %s docs", len(ids))
        return {**state, "memory_writeback_ids": ids, "current_phase": "complete"}
    except Exception as e:
        logger.error("memory_writeback_node failed: %s", e, exc_info=True)
        return {**state, "memory_writeback_ids": [], "current_phase": "complete"}


def route_after_orchestrator(_state: AgentState) -> str:
    """Always retrieve org memory before downstream agents."""
    return "org_memory"


def route_after_org_memory(state: AgentState) -> str:
    """Route to the agent selected by the orchestrator."""
    next_agent = state.get("next_agent") or "decision"
    if next_agent in ("prd_writer", "prd_generation"):
        return "prd_writer"
    if next_agent == "stress_test":
        return "stress_test"
    # decision / full_pipeline / default
    return "decision"


def build_workflow():
    """
    Build and compile the LangGraph workflow.

    START → orchestrator → org_memory → [decision|prd_writer|stress_test]
      decision → prd_writer → stress_test → memory_writeback → END
      prd_writer → stress_test → memory_writeback → END
      stress_test → memory_writeback → END
    """
    workflow = StateGraph(AgentState)

    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("org_memory", org_memory_node)
    workflow.add_node("decision", decision_node)
    workflow.add_node("prd_writer", prd_writer_node)
    workflow.add_node("stress_test", stress_test_node)
    workflow.add_node("memory_writeback", memory_writeback_node)

    workflow.set_entry_point("orchestrator")

    workflow.add_conditional_edges(
        "orchestrator",
        route_after_orchestrator,
        {"org_memory": "org_memory"},
    )
    workflow.add_conditional_edges(
        "org_memory",
        route_after_org_memory,
        {
            "decision": "decision",
            "prd_writer": "prd_writer",
            "stress_test": "stress_test",
        },
    )

    workflow.add_edge("decision", "prd_writer")
    workflow.add_edge("prd_writer", "stress_test")
    workflow.add_edge("stress_test", "memory_writeback")
    workflow.add_edge("memory_writeback", END)

    app = workflow.compile()
    logger.info("Workflow compiled successfully")
    return app


async def run_workflow_streaming(
    workflow,
    user_message: str,
    session_id: str,
    phase: str = "auto",
    message_history: Optional[list] = None,
) -> AsyncIterator[dict]:
    """Execute the workflow and yield streaming SSE events."""
    if message_history:
        initial_messages = list(message_history)
        if not initial_messages or not isinstance(initial_messages[-1], HumanMessage):
            initial_messages.append(HumanMessage(content=user_message))
    else:
        initial_messages = [HumanMessage(content=user_message)]

    initial_state: AgentState = {
        "messages": initial_messages,
        "current_phase": phase or "auto",
        "decision_output": None,
        "prd_output": None,
        "stress_test_results": None,
        "stress_test_summary": None,
        "critic_feedback": None,
        "org_memory_context": None,
        "org_history_context": None,
        "org_profile": None,
        "org_profile_text": None,
        "memory_citations": None,
        "memory_writeback_ids": None,
        "next_agent": None,
        "user_input": user_message,
    }

    executed_agents = set()

    try:
        async for event in workflow.astream(initial_state):
            for node_name, state_update in event.items():
                logger.info("Workflow: Node '%s' completed", node_name)

                yield {
                    "type": "agent_start",
                    "data": {"agent": node_name, "session_id": session_id},
                }

                output_data: dict[str, Any] = {}
                if state_update:
                    if "decision_output" in state_update:
                        output_data["decision"] = state_update["decision_output"]
                    if "prd_output" in state_update:
                        output_data["prd"] = state_update["prd_output"]
                    if "stress_test_results" in state_update:
                        output_data["stress_test"] = state_update["stress_test_results"]
                        output_data["stress_test_summary"] = state_update.get(
                            "stress_test_summary"
                        )
                    if "memory_citations" in state_update:
                        output_data["citations"] = state_update.get("memory_citations") or []
                    if "org_profile" in state_update and state_update.get("org_profile"):
                        profile = state_update["org_profile"]
                        output_data["org_profile_summary"] = {
                            "terminology": (profile.get("terminology") or {}).get("mapping", {}),
                            "lessons_count": len(profile.get("lessons_learned") or []),
                            "review_focus": (profile.get("review_focus") or {}).get(
                                "top_3_dimensions", []
                            ),
                        }
                    if "memory_writeback_ids" in state_update:
                        output_data["writeback_ids"] = state_update.get("memory_writeback_ids")

                yield {
                    "type": "agent_output",
                    "data": {
                        "agent": node_name,
                        "output": output_data,
                        "session_id": session_id,
                    },
                }
                yield {
                    "type": "agent_complete",
                    "data": {"agent": node_name, "session_id": session_id},
                }
                executed_agents.add(node_name)
    except Exception as e:
        logger.error("Workflow execution error: %s: %s", type(e).__name__, e, exc_info=True)
        yield {
            "type": "error",
            "data": f"工作流执行出错: {type(e).__name__}: {str(e)}",
        }
        return

    yield {
        "type": "done",
        "data": {
            "session_id": session_id,
            "agents_executed": list(executed_agents),
        },
    }
