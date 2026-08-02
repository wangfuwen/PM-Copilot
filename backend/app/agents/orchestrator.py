"""
Orchestrator Agent — 意图识别与路由决策。

The orchestrator is the entry point of the multi-agent workflow.
It analyzes the user\'s intent and routes to the appropriate agent(s):
- "decision" → Decision Agent for requirement analysis
- "prd_generation" → PRD Writer Agent for document generation
- "stress_test" → Stress Test Lead for PRD challenge
- "full_pipeline" → Decision → PRD → Stress Test (complete flow)
"""

import logging
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.language_models import BaseChatModel

from app.config import settings
from app.models.schemas import ChatRequest

logger = logging.getLogger(__name__)

# Intent classification prompt
ORCHESTRATOR_PROMPT = """\
你是一个意图识别助手。根据用户的输入，判断用户想要执行的任务类型。

可选任务类型：
1. **decision** — 用户想要分析和评估一个产品需求，获取决策建议
2. **prd_generation** — 用户已经明确了需求，想要生成 PRD 文档
3. **stress_test** — 用户已经有了 PRD，想要进行压力测试和红队挑战
4. **full_pipeline** — 用户提出了一个新需求，想要走完整流程（分析→PRD→测试）

判断规则：
- 如果用户描述了一个新想法/需求并请求分析 → full_pipeline
- 如果用户明确说"帮我分析这个需求" → decision
- 如果用户说"帮我写 PRD" 或 "生成需求文档" → prd_generation
- 如果用户说"帮我压力测试" 或 "挑战一下这个方案" → stress_test
- 如果不确定，默认 → full_pipeline

请只输出任务类型名称，不要输出其他内容。
"""


class OrchestratorAgent:
    """
    Orchestrator Agent that routes user intents to the appropriate downstream agents.

    Attributes:
        llm: The language model used for intent classification.
    """

    def __init__(self, llm: BaseChatModel):
        """
        Initialize the Orchestrator Agent.

        Args:
            llm: A LangChain chat model instance.
        """
        self.llm = llm

    async def classify_intent(self, user_message: str, forced_phase: str | None = None) -> str:
        """
        Classify the user\'s intent.

        Args:
            user_message: The user\'s input message.
            forced_phase: If set, bypass classification and return this phase directly.

        Returns:
            One of: "decision", "prd_generation", "stress_test", "full_pipeline"
        """
        if forced_phase and forced_phase != "auto":
            logger.info(f"Forced phase: {forced_phase}")
            return forced_phase

        messages = [
            SystemMessage(content=ORCHESTRATOR_PROMPT),
            AIMessage(content="请分析以下用户输入并输出任务类型："),
        ]
        # Use user message as the last human message
        from langchain_core.messages import HumanMessage
        messages.append(HumanMessage(content=user_message))

        response = await self.llm.ainvoke(messages)
        intent = response.content.strip().lower()

        # Normalize intent
        valid_intents = {"decision", "prd_generation", "stress_test", "full_pipeline"}
        if intent not in valid_intents:
            # Try to find a partial match
            for vi in valid_intents:
                if vi in intent:
                    intent = vi
                    break
            else:
                intent = "full_pipeline"  # Default

        logger.info(f"Classified intent: {intent}")
        return intent

    async def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        LangGraph node function for the orchestrator.

        Args:
            state: Current workflow state.

        Returns:
            Updated state with next_agent determined.
        """
        from langchain_core.messages import HumanMessage

        # Get the last user message
        user_message = ""
        for msg in reversed(state.get("messages", [])):
            if isinstance(msg, HumanMessage):
                user_message = msg.content
                break

        if not user_message:
            user_message = state.get("user_input", "")

        phase = state.get("current_phase", "auto")
        intent = await self.classify_intent(user_message, forced_phase=phase)

        # Map intent to next agent
        routing_map = {
            "decision": "decision",
            "prd_generation": "prd_writer",
            "stress_test": "stress_test",
            "full_pipeline": "decision",  # Start from decision in full pipeline
        }

        next_agent = routing_map.get(intent, "decision")

        return {
            **state,
            "current_phase": intent if intent != "full_pipeline" else "decision",
            "next_agent": next_agent,
            "user_input": user_message,
        }
