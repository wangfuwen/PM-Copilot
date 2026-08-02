"""
Basic tests for PM Copilot workflow.

Tests the workflow structure, state management, and agent initialization.
Run with: pytest tests/ -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.schemas import (
    DecisionOutput,
    StressTestChallenge,
    StressTestOutput,
    ChatRequest,
    MemorySearchRequest,
    MemoryStoreRequest,
)
from app.graph.workflow import (
    AgentState,
    build_workflow,
    route_after_orchestrator,
    route_after_org_memory,
    route_after_decision,
    route_after_critic,
)


# ──────────────────────────────────────────────
# Schema Tests
# ──────────────────────────────────────────────

class TestSchemas:
    """Test Pydantic data models."""

    def test_decision_output_creation(self):
        """Test DecisionOutput can be created with valid data."""
        decision = DecisionOutput(
            five_w_one_h={
                "what": "Build a chat app",
                "why": "Users need real-time communication",
                "who": "Young professionals",
                "when": "Q1 2025",
                "where": "Mobile and web",
                "how": "React + WebSocket",
            },
            recommendation="GO",
            reasoning="Clear need, feasible implementation, good market timing.",
            risks=["Competitive market", "User retention challenge"],
            confidence=0.85,
        )
        assert decision.recommendation == "GO"
        assert decision.confidence == 0.85
        assert len(decision.risks) == 2

    def test_stress_test_output(self):
        """Test StressTestOutput structure."""
        challenge = StressTestChallenge(
            role="👔 老板",
            challenge="ROI 不明确",
            severity="high",
            suggestions=["补充 ROI 计算", "明确变现路径"],
        )
        output = StressTestOutput(
            challenges=[challenge],
            overall_score=65.0,
            summary="需要补充商业论证",
        )
        assert output.overall_score == 65.0
        assert len(output.challenges) == 1

    def test_chat_request(self):
        """Test ChatRequest validation."""
        req = ChatRequest(message="帮我分析一个需求")
        assert req.message == "帮我分析一个需求"
        assert req.phase == "auto"

    def test_memory_search_request(self):
        """Test MemorySearchRequest validation."""
        req = MemorySearchRequest(query="电商产品 PRD", top_k=3)
        assert req.query == "电商产品 PRD"
        assert req.top_k == 3


# ──────────────────────────────────────────────
# Workflow Tests
# ──────────────────────────────────────────────

class TestWorkflow:
    """Test LangGraph workflow structure."""

    def test_build_workflow(self):
        """Test that the workflow can be built without errors."""
        workflow = build_workflow()
        assert workflow is not None

    def test_route_after_orchestrator_always_org_memory(self):
        """Orchestrator always routes through org memory first."""
        assert route_after_orchestrator({"next_agent": "decision"}) == "org_memory"
        assert route_after_orchestrator({"next_agent": "prd_writer"}) == "org_memory"
        assert route_after_orchestrator({"next_agent": "stress_test"}) == "org_memory"

    def test_route_after_org_memory(self):
        """After retrieval, route to the orchestrator-selected agent."""
        assert route_after_org_memory({"next_agent": "decision"}) == "decision"
        assert route_after_org_memory({"next_agent": "prd_writer"}) == "prd_writer"
        assert route_after_org_memory({"next_agent": "prd_generation"}) == "prd_writer"
        assert route_after_org_memory({"next_agent": "stress_test"}) == "stress_test"
        assert route_after_org_memory({"next_agent": "unknown"}) == "decision"

    def test_route_after_decision_clarify_or_continue(self):
        assert route_after_decision({"awaiting_clarification": True}) == "end"
        assert route_after_decision({"requested_phase": "decision"}) == "end"
        assert route_after_decision({"requested_phase": "auto"}) == "prd_writer"
        assert route_after_decision({"requested_phase": "full_pipeline"}) == "prd_writer"

    def test_route_after_critic(self):
        assert route_after_critic({"skip_stress": True}) == "stress_test"
        assert route_after_critic({"demo_mode": True}) == "stress_test"


# ──────────────────────────────────────────────
# Agent Tests (mocked LLM)
# ──────────────────────────────────────────────

class TestAgents:
    """Test agent logic with mocked LLM calls."""

    @pytest.fixture
    def mock_llm(self):
        """Create a mock LLM that returns predefined responses."""
        llm = AsyncMock()
        llm.ainvoke = AsyncMock()
        return llm

    @pytest.mark.asyncio
    async def test_decision_agent(self, mock_llm):
        """Test Decision Agent with mock LLM."""
        from app.agents.decision import DecisionAgent
        from langchain_core.messages import AIMessage

        mock_llm.ainvoke.return_value = AIMessage(content="""
```json
{
  "five_w_one_h": {"what": "test", "why": "test", "who": "test", "when": "test", "where": "test", "how": "test"},
  "recommendation": "GO",
  "reasoning": "Good idea",
  "risks": ["competition"],
  "confidence": 0.9
}
```
""")
        mock_llm.bind = MagicMock(return_value=mock_llm)

        agent = DecisionAgent(llm=mock_llm)
        result = await agent.analyze("Build a new feature")
        assert result.recommendation == "GO"
        assert result.confidence == 0.9

    def test_progressive_clarify_qa_and_skip(self):
        from app.agents.decision import (
            DecisionAgent,
            CLARIFY_MARKER,
            format_clarify_step,
            MAX_CLARIFY_STEPS,
        )
        from langchain_core.messages import AIMessage, HumanMessage

        step = {
            "mode": "clarify_step",
            "step": 1,
            "max_steps": MAX_CLARIFY_STEPS,
            "id": "who_pays",
            "question": "主要付费方是谁？",
            "options": [
                {"id": "b2c", "label": "个人用户付费"},
                {"id": "b2b", "label": "企业采购"},
            ],
            "allow_custom": True,
        }
        clarify_msg = format_clarify_step(step)
        assert CLARIFY_MARKER in clarify_msg

        unanswered = [
            HumanMessage(content="做一个 AI 笔记应用"),
            AIMessage(content=clarify_msg),
        ]
        assert DecisionAgent._last_unanswered_clarify(unanswered) is not None
        assert DecisionAgent._extract_qa_pairs(unanswered) == []

        answered = unanswered + [HumanMessage(content="个人用户付费")]
        assert DecisionAgent._last_unanswered_clarify(answered) is None
        pairs = DecisionAgent._extract_qa_pairs(answered)
        assert len(pairs) == 1
        assert pairs[0]["answer"] == "个人用户付费"
        assert DecisionAgent._is_skip_answer("__SKIP_CLARIFY__") is True
        assert DecisionAgent._is_skip_answer("跳过，直接决策") is True
        assert DecisionAgent._is_skip_answer("个人用户付费") is False

    def test_normalize_clarify_step_fallback(self):
        from app.agents.decision import DecisionAgent

        out = DecisionAgent._normalize_step({"action": "ask"}, step=1)
        assert out["action"] == "ask"
        assert out["question"]
        assert len(out["options"]) >= 2

        decide = DecisionAgent._normalize_step(
            {"action": "decide", "reason": "enough"}, step=1
        )
        assert decide["action"] == "decide"

    @pytest.mark.asyncio
    async def test_stress_test_agent(self, mock_llm):
        """Test Stress Test Agent with mock LLM."""
        from app.agents.stress_test import StressTestAgent
        from langchain_core.messages import AIMessage

        mock_llm.ainvoke.return_value = AIMessage(content="""
挑战: 这个方案的 ROI 不够清晰。
严重度: high
建议: 1. 补充 ROI 计算 2. 明确 KPI
""")

        agent = StressTestAgent(llm=mock_llm)
        result = await agent.run_stress_test("# Test PRD\nSome content here")
        assert len(result.challenges) == 5  # One per role
        assert result.overall_score >= 0
