"""
LangGraph Workflow — 核心 Multi-Agent 编排逻辑。

Orchestrator → Org Memory → Decision(clarify|decide) → PRD → Critic → Evaluator → Stress → Writeback → END
"""

from __future__ import annotations

import logging
from typing import Any, Optional, AsyncIterator, Callable, Awaitable

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from typing_extensions import TypedDict

from app.config import settings
from app.telemetry import RunTelemetry, get_tracker, set_tracker

logger = logging.getLogger(__name__)

NODE_NAMES = {
    "orchestrator",
    "org_memory",
    "decision",
    "prd_writer",
    "critic",
    "evaluator",
    "stress_test",
    "memory_writeback",
}


class AgentState(TypedDict, total=False):
    messages: list[BaseMessage]
    current_phase: str
    decision_output: Optional[dict]
    clarifying_questions: Optional[dict]
    awaiting_clarification: Optional[bool]
    prd_output: Optional[str]
    stress_test_results: Optional[list]
    stress_test_summary: Optional[dict]
    critic_feedback: Optional[dict]
    evaluation: Optional[dict]
    org_memory_context: Optional[str]
    org_history_context: Optional[str]
    org_profile: Optional[dict]
    org_profile_text: Optional[str]
    memory_citations: Optional[list]
    memory_empty: Optional[bool]
    memory_writeback_ids: Optional[list]
    next_agent: Optional[str]
    user_input: Optional[str]
    original_requirement: Optional[str]
    accepted_issues: Optional[list[str]]
    prd_revision: Optional[bool]
    skip_clarify: Optional[bool]
    demo_mode: Optional[bool]
    skip_stress: Optional[bool]
    requested_phase: Optional[str]
    last_agent_metrics: Optional[dict]


def _instrument(name: str, fn: Callable[[AgentState], Awaitable[dict]]):
    """Wrap a node to record duration / status on the active RunTelemetry."""

    async def wrapped(state: AgentState) -> dict:
        tracker = get_tracker()
        if tracker:
            tracker.begin(name)
        try:
            result = await fn(state)
            metrics = tracker.end(name) if tracker else None
            out = dict(result or {})
            if metrics:
                out["last_agent_metrics"] = metrics.to_dict()
            return out
        except Exception as e:
            if tracker:
                metrics = tracker.end(name, error=f"{type(e).__name__}: {e}")
                # Re-raise so workflow surfaces error; metrics still available via tracker
            raise

    wrapped.__name__ = f"{name}_instrumented"
    return wrapped


def get_llm(agent_name: str = None, demo_mode: bool = False):
    """Get LLM; in demo mode force mini models for cost control."""
    if demo_mode or settings.demo_mode:
        mini = f"openai:{settings.openai_model_mini}"
        # Temporarily override via creating model directly
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.openai_model_mini,
            openai_api_key=settings.openai_api_key,
            temperature=0.7,
            timeout=60,
        )
    return settings.get_llm(agent_name=agent_name)


async def orchestrator_node(state: AgentState) -> dict:
    from app.agents.orchestrator import OrchestratorAgent

    try:
        llm = get_llm("orchestrator", demo_mode=bool(state.get("demo_mode")))
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
        llm = get_llm("org_memory", demo_mode=bool(state.get("demo_mode")))
        vs = get_vector_store()
        agent = OrgMemoryAgent(llm=llm, vector_store=vs)
        result = await agent(state)
        empty = vs.collection.count() == 0
        result["memory_empty"] = empty
        if empty:
            result["org_memory_context"] = result.get("org_memory_context") or ""
            logger.info("org_memory_node: knowledge base is empty")
        logger.info(
            "org_memory_node: context_found=%s citations=%s empty=%s",
            bool(result.get("org_memory_context")),
            len(result.get("memory_citations") or []),
            empty,
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
            "memory_empty": True,
        }


async def decision_node(state: AgentState) -> dict:
    from app.agents.decision import DecisionAgent, format_clarify_step

    llm = get_llm("decision", demo_mode=bool(state.get("demo_mode")))
    agent = DecisionAgent(llm=llm)
    result = await agent(state)

    messages = list(state.get("messages", []))
    if result.get("awaiting_clarification") and result.get("clarifying_questions"):
        text = format_clarify_step(result["clarifying_questions"])
        # Avoid duplicating the same unanswered step in history
        if not (
            messages
            and isinstance(messages[-1], AIMessage)
            and messages[-1].content == text
        ):
            messages.append(AIMessage(content=text, name="decision_agent"))
        logger.info("decision_node: awaiting clarification step")
        return {**result, "messages": messages}

    decision = result.get("decision_output", {}) or {}
    summary = (
        f"决策建议: {decision.get('recommendation', 'N/A')} - "
        f"{decision.get('reasoning', '')[:200]}"
    )
    messages.append(AIMessage(content=summary, name="decision_agent"))
    logger.info("decision_node: recommendation=%s", decision.get("recommendation"))
    return {**result, "messages": messages}


async def prd_writer_node(state: AgentState) -> dict:
    from app.agents.prd_writer import PRDWriterAgent

    llm = get_llm("prd_writer", demo_mode=bool(state.get("demo_mode")))
    agent = PRDWriterAgent(llm=llm)
    result = await agent(state)
    prd = result.get("prd_output", "")
    messages = list(state.get("messages", []))
    messages.append(AIMessage(content=f"PRD 已生成 ({len(prd)} 字)", name="prd_writer_agent"))
    return {**result, "messages": messages}


async def critic_node(state: AgentState) -> dict:
    from app.agents.critic import CriticAgent

    llm = get_llm("critic", demo_mode=bool(state.get("demo_mode")))
    agent = CriticAgent(llm=llm)
    result = await agent(state)
    feedback = result.get("critic_feedback") or {}
    messages = list(state.get("messages", []))
    if feedback.get("review"):
        messages.append(AIMessage(content=feedback["review"], name="critic_agent"))
    logger.info(
        "critic_node: verdict=%s score=%s",
        feedback.get("verdict"),
        feedback.get("score"),
    )
    return {**result, "messages": messages}


async def evaluator_node(state: AgentState) -> dict:
    from app.agents.evaluator import EvaluatorAgent

    llm = get_llm("critic", demo_mode=bool(state.get("demo_mode")))
    agent = EvaluatorAgent(llm=llm)
    result = await agent(state)
    evaluation = result.get("evaluation") or {}
    messages = list(state.get("messages", []))
    if evaluation.get("report"):
        messages.append(
            AIMessage(content=evaluation["report"], name="evaluator_agent")
        )
    logger.info(
        "evaluator_node: target=%s overall=%s verdict=%s",
        evaluation.get("target"),
        evaluation.get("overall"),
        evaluation.get("verdict"),
    )
    return {**result, "messages": messages}


async def stress_test_node(state: AgentState) -> dict:
    from app.agents.stress_test import StressTestAgent

    if state.get("skip_stress") or (
        (state.get("demo_mode") or settings.demo_mode) and settings.demo_skip_stress
    ):
        logger.info("stress_test_node: skipped (demo mode)")
        messages = list(state.get("messages", []))
        messages.append(
            AIMessage(
                content="演示模式已跳过压力测试（节省成本）。关闭演示模式可启用 5 角色红队挑战。",
                name="stress_test_agent",
            )
        )
        return {
            **state,
            "stress_test_results": [],
            "stress_test_summary": {
                "overall_score": None,
                "summary": "skipped_in_demo_mode",
                "skipped": True,
            },
            "messages": messages,
            "current_phase": "complete",
        }

    llm = get_llm("stress_test", demo_mode=bool(state.get("demo_mode")))
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
    """No-op: org memory is upload-only; do not index chat/workflow outputs."""
    from app.agents.org_memory import write_back_results

    try:
        llm = get_llm("org_memory", demo_mode=bool(state.get("demo_mode")))
        ids = await write_back_results(state, llm)
        logger.info("memory_writeback_node: upload-only mode, wrote %s docs", len(ids))
        return {
            **state,
            "memory_writeback_ids": ids,
            "current_phase": "complete",
        }
    except Exception as e:
        logger.error("memory_writeback_node failed: %s", e, exc_info=True)
        return {**state, "memory_writeback_ids": [], "current_phase": "complete"}


def route_after_orchestrator(_state: AgentState) -> str:
    return "org_memory"


def route_after_org_memory(state: AgentState) -> str:
    next_agent = state.get("next_agent") or "decision"
    if next_agent in ("prd_writer", "prd_generation"):
        return "prd_writer"
    if next_agent == "stress_test":
        return "stress_test"
    return "decision"


def route_after_decision(state: AgentState) -> str:
    if state.get("awaiting_clarification"):
        return "end"
    # Decision-only and non-GO decisions stop at the gate for user confirmation.
    requested = (state.get("requested_phase") or "auto").lower()
    recommendation = ((state.get("decision_output") or {}).get("recommendation") or "").upper()
    if requested == "decision" or recommendation in {"PIVOT", "KILL"}:
        return "evaluator"
    return "prd_writer"


def route_after_evaluator(state: AgentState) -> str:
    """After scoring: PRD path continues to stress; decision-only ends."""
    if state.get("prd_output"):
        return "stress_test"
    return "end"


def build_workflow():
    """
    START → orchestrator → org_memory → [decision|prd|stress]
      decision → (clarify END) | evaluator | prd → critic → evaluator → stress → writeback
    """
    workflow = StateGraph(AgentState)

    workflow.add_node("orchestrator", _instrument("orchestrator", orchestrator_node))
    workflow.add_node("org_memory", _instrument("org_memory", org_memory_node))
    workflow.add_node("decision", _instrument("decision", decision_node))
    workflow.add_node("prd_writer", _instrument("prd_writer", prd_writer_node))
    workflow.add_node("critic", _instrument("critic", critic_node))
    workflow.add_node("evaluator", _instrument("evaluator", evaluator_node))
    workflow.add_node("stress_test", _instrument("stress_test", stress_test_node))
    workflow.add_node(
        "memory_writeback", _instrument("memory_writeback", memory_writeback_node)
    )

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
    workflow.add_conditional_edges(
        "decision",
        route_after_decision,
        {"prd_writer": "prd_writer", "evaluator": "evaluator", "end": END},
    )
    workflow.add_edge("prd_writer", "critic")
    workflow.add_edge("critic", "evaluator")
    workflow.add_conditional_edges(
        "evaluator",
        route_after_evaluator,
        {"stress_test": "stress_test", "end": END},
    )
    workflow.add_edge("stress_test", "memory_writeback")
    workflow.add_edge("memory_writeback", END)

    app = workflow.compile()
    logger.info("Workflow compiled successfully")
    return app


def build_node_output(node_name: str, state_update: Any) -> dict[str, Any]:
    """Expose only artifacts produced by the completed node, not carried state."""
    if not isinstance(state_update, dict):
        return {}

    output_data: dict[str, Any] = {}
    if node_name == "decision":
        if state_update.get("clarifying_questions"):
            output_data["clarifying_questions"] = state_update[
                "clarifying_questions"
            ]
            output_data["awaiting_clarification"] = True
        if state_update.get("decision_output"):
            output_data["decision"] = state_update["decision_output"]
    elif node_name == "prd_writer":
        if "prd_output" in state_update and state_update.get("prd_output") is not None:
            output_data["prd"] = state_update["prd_output"]
            output_data["prd_revision"] = bool(state_update.get("prd_revision"))
    elif node_name == "critic" and state_update.get("critic_feedback"):
        output_data["critic"] = state_update["critic_feedback"]
    elif node_name == "evaluator" and state_update.get("evaluation"):
        output_data["evaluation"] = state_update["evaluation"]
    elif node_name == "stress_test" and "stress_test_results" in state_update:
        output_data["stress_test"] = state_update["stress_test_results"]
        output_data["stress_test_summary"] = state_update.get("stress_test_summary")
    elif node_name == "memory_writeback" and "memory_writeback_ids" in state_update:
        output_data["writeback_ids"] = state_update.get("memory_writeback_ids")

    if node_name == "org_memory":
        if "memory_citations" in state_update:
            output_data["citations"] = state_update.get("memory_citations") or []
        if state_update.get("memory_empty") is not None:
            output_data["memory_empty"] = state_update.get("memory_empty")
        if state_update.get("org_profile"):
            profile = state_update["org_profile"]
            output_data["org_profile_summary"] = {
                "terminology": (profile.get("terminology") or {}).get("mapping", {}),
                "lessons_count": len(profile.get("lessons_learned") or []),
                "review_focus": (profile.get("review_focus") or {}).get(
                    "top_3_dimensions", []
                ),
            }

    return output_data


async def run_workflow_streaming(
    workflow,
    user_message: str,
    session_id: str,
    phase: str = "auto",
    message_history: Optional[list] = None,
    demo_mode: bool = False,
    skip_clarify: bool = False,
    resume_context: Optional[dict] = None,
) -> AsyncIterator[dict]:
    resume_context = dict(resume_context or {})
    if message_history:
        initial_messages = list(message_history)
        if not initial_messages or not isinstance(initial_messages[-1], HumanMessage):
            initial_messages.append(HumanMessage(content=user_message))
    else:
        initial_messages = [HumanMessage(content=user_message)]

    skip_stress = bool(demo_mode and settings.demo_skip_stress) or (
        settings.demo_mode and settings.demo_skip_stress
    )

    restored_prd = resume_context.get("prd_output")
    if not restored_prd and (phase or "auto").lower() == "stress_test":
        # Direct stress-test mode also accepts a pasted PRD as the current message.
        if len((user_message or "").strip()) >= 100:
            restored_prd = user_message

    initial_state: AgentState = {
        "messages": initial_messages,
        "current_phase": phase or "auto",
        "decision_output": resume_context.get("decision_output"),
        "clarifying_questions": None,
        "awaiting_clarification": False,
        "prd_output": restored_prd,
        "stress_test_results": None,
        "stress_test_summary": None,
        "critic_feedback": None,
        "evaluation": None,
        "org_memory_context": None,
        "org_history_context": None,
        "org_profile": None,
        "org_profile_text": None,
        "memory_citations": None,
        "memory_empty": None,
        "memory_writeback_ids": None,
        "next_agent": None,
        "user_input": user_message,
        "original_requirement": resume_context.get("original_requirement") or user_message,
        "accepted_issues": resume_context.get("accepted_issues") or [],
        "prd_revision": False,
        "skip_clarify": skip_clarify,
        "demo_mode": demo_mode or settings.demo_mode,
        "skip_stress": skip_stress,
        "requested_phase": phase or "auto",
        "last_agent_metrics": None,
    }

    executed_agents = set()
    tracker = RunTelemetry()
    set_tracker(tracker)

    try:
        from datetime import datetime, timezone, timedelta

        async for event in workflow.astream(initial_state):
            for node_name, state_update in event.items():
                if node_name not in NODE_NAMES:
                    continue
                logger.info("Workflow: Node '%s' completed", node_name)

                metrics = None
                if isinstance(state_update, dict):
                    metrics = state_update.get("last_agent_metrics")
                if not metrics and node_name in tracker.nodes:
                    metrics = tracker.nodes[node_name].to_dict()

                duration_ms = (metrics or {}).get("duration_ms") or 0
                completed_at = datetime.now(timezone.utc)
                started_at = completed_at - timedelta(milliseconds=duration_ms)

                yield {
                    "type": "agent_start",
                    "data": {
                        "agent": node_name,
                        "session_id": session_id,
                        "started_at": started_at.isoformat(),
                    },
                }

                output_data = build_node_output(node_name, state_update)

                yield {
                    "type": "agent_output",
                    "data": {
                        "agent": node_name,
                        "output": output_data,
                        "session_id": session_id,
                        "metrics": metrics,
                    },
                }
                yield {
                    "type": "agent_complete",
                    "data": {
                        "agent": node_name,
                        "session_id": session_id,
                        "started_at": started_at.isoformat(),
                        "completed_at": completed_at.isoformat(),
                        "metrics": metrics,
                    },
                }
                executed_agents.add(node_name)
    except Exception as e:
        logger.error(
            "Workflow execution error: %s: %s", type(e).__name__, e, exc_info=True
        )
        yield {
            "type": "error",
            "data": f"工作流执行出错: {type(e).__name__}: {str(e)}",
        }
        return
    finally:
        set_tracker(None)

    yield {
        "type": "done",
        "data": {
            "session_id": session_id,
            "agents_executed": list(executed_agents),
            "run_metrics": {a: m.to_dict() for a, m in tracker.nodes.items()},
            "total_tokens": sum(m.total_tokens for m in tracker.nodes.values()),
            "total_duration_ms": sum(m.duration_ms for m in tracker.nodes.values()),
        },
    }
