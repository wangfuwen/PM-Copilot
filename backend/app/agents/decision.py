"""
Decision Agent — 需求决策顾问。

Analyzes product requirements using the 5W1H framework and provides
structured decision recommendations (GO / PIVOT / KILL).
"""

import json
import logging
import re
from typing import Any

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.language_models import BaseChatModel

from app.models.schemas import DecisionOutput
from app.prompts.decision import DECISION_SYSTEM_PROMPT, DECISION_USER_PROMPT

logger = logging.getLogger(__name__)


class DecisionAgent:
    """
    Decision Agent that analyzes product requirements and provides GO/PIVOT/KILL recommendations.

    Uses the 5W1H framework to systematically evaluate:
    - Requirement clarity
    - Business value
    - Technical feasibility
    - Risk level
    - Competitive differentiation

    Attributes:
        llm: The language model used for analysis.
    """

    def __init__(self, llm: BaseChatModel):
        """
        Initialize the Decision Agent.

        Args:
            llm: A LangChain chat model instance.
        """
        self.llm = llm

    async def analyze(
        self,
        user_requirement: str,
        org_memory_context: str = "",
        org_profile_text: str = "",
    ) -> DecisionOutput:
        """
        Analyze a product requirement and return a structured decision.

        Args:
            user_requirement: The product requirement description.
            org_memory_context: Optional context from organizational memory.
            org_profile_text: Optional Org Profile JSON/text.

        Returns:
            DecisionOutput with 5W1H analysis and GO/PIVOT/KILL recommendation.
        """
        profile_block = ""
        if org_profile_text:
            profile_block = f"\n\n## 组织画像（Org Profile）\n{org_profile_text}"

        rag_block = ""
        if org_memory_context:
            rag_block = f"\n\n## 检索到的相关历史文档\n{org_memory_context}"

        system_prompt = (
            DECISION_SYSTEM_PROMPT
            .replace("{org_profile}", profile_block)
            .replace("{rag_snippets}", rag_block)
        )
        user_prompt = DECISION_USER_PROMPT.replace("{user_requirement}", user_requirement)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        # Prompt already requires JSON; avoid bind(model_kwargs=...) which breaks
        # on newer openai/langchain-openai combinations.
        try:
            json_llm = self.llm.bind(response_format={"type": "json_object"})
            response = await json_llm.ainvoke(messages)
        except Exception:
            # Fallback if bind/response_format is unsupported by the runtime/mock
            response = await self.llm.ainvoke(messages)
        content = response.content

        # Parse JSON from response (handle markdown code blocks)
        content = self._extract_json(content)

        try:
            decision = DecisionOutput.model_validate_json(content)
        except Exception as e:
            logger.warning(f"Failed to parse decision output: {e}, using fallback")
            decision = DecisionOutput(
                five_w_one_h={"what": user_requirement},
                recommendation="PIVOT",
                reasoning=content if content else "无法解析决策输出，建议人工复核。",
                risks=["解析失败，需要人工审核"],
                confidence=0.3,
            )

        return decision

    async def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        LangGraph node function for the Decision Agent.

        Args:
            state: Current workflow state.

        Returns:
            Updated state with decision_output populated.
        """
        user_input = state.get("user_input", "")
        org_context = state.get("org_memory_context", "")
        org_profile_text = state.get("org_profile_text", "") or ""

        logger.info("DecisionAgent: Analyzing requirement...")
        decision = await self.analyze(user_input, org_context, org_profile_text)
        logger.info(f"DecisionAgent: Recommendation = {decision.recommendation}")

        return {
            **state,
            "decision_output": decision.model_dump(),
            "current_phase": "prd_generation",
            "next_agent": "prd_writer",
        }

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extract JSON from text using multiple strategies."""
        text = text.strip()

        # Strategy 1: markdown code block
        for marker in ["```json", "```"]:
            if marker in text:
                start = text.index(marker) + len(marker)
                end = text.index("```", start)
                candidate = text[start:end].strip()
                if candidate.startswith("{"):
                    return candidate

        # Strategy 2: regex find first {...} block (handles nested braces)
        match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
        if match:
            candidate = match.group(0).strip()
            # Validate it's real JSON
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                pass

        # Strategy 3: try to find JSON by scanning from first { to last }
        if "{" in text and "}" in text:
            start = text.index("{")
            end = text.rindex("}") + 1
            candidate = text[start:end].strip()
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                pass

        # Strategy 4: return as-is (will trigger fallback in caller)
        return text
