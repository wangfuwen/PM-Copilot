"""
PRD Writer Agent — 产品需求文档生成。

Generates structured, professional PRDs based on decision analysis output
and organizational memory (historical templates and patterns).
"""

import logging
from typing import Any

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.language_models import BaseChatModel

from app.prompts.prd import PRD_SYSTEM_PROMPT, PRD_USER_PROMPT

logger = logging.getLogger(__name__)


class PRDWriterAgent:
    """
    PRD Writer Agent that generates comprehensive Product Requirement Documents.

    Produces structured PRDs with:
    - Background & objectives (OKR format)
    - User personas & stories
    - Prioritized feature requirements (P0/P1/P2)
    - Non-functional requirements
    - Technical recommendations
    - Roadmap & risk assessment

    Attributes:
        llm: The language model used for PRD generation.
    """

    def __init__(self, llm: BaseChatModel):
        """
        Initialize the PRD Writer Agent.

        Args:
            llm: A LangChain chat model instance.
        """
        self.llm = llm

    async def generate(
        self,
        user_requirement: str,
        decision_output: dict | None = None,
        org_memory_context: str = "",
        org_profile_text: str = "",
    ) -> str:
        """
        Generate a PRD based on requirements and decision analysis.

        Args:
            user_requirement: Original user requirement description.
            decision_output: Structured decision from Decision Agent.
            org_memory_context: Relevant historical context from org memory.
            org_profile_text: Optional Org Profile JSON/text.

        Returns:
            Complete PRD document as a formatted string.
        """
        profile_block = ""
        if org_profile_text:
            profile_block = f"\n\n## 组织画像（Org Profile）\n{org_profile_text}"

        rag_block = ""
        if org_memory_context:
            rag_block = f"\n\n## 检索到的相关历史 PRD\n{org_memory_context}"

        system_prompt = (
            PRD_SYSTEM_PROMPT
            .replace("{org_profile}", profile_block)
            .replace("{rag_snippets}", rag_block)
        )

        # Format decision output for the prompt
        decision_str = ""
        if decision_output:
            import json
            decision_str = json.dumps(decision_output, ensure_ascii=False, indent=2)
        else:
            decision_str = "（未进行前置决策分析，请直接基于需求描述生成 PRD）"

        user_prompt = (
            PRD_USER_PROMPT
            .replace("{user_requirement}", user_requirement)
            .replace("{decision_output}", decision_str)
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        response = await self.llm.ainvoke(messages)
        prd_content = response.content

        logger.info(f"PRDWriterAgent: Generated PRD ({len(prd_content)} chars)")
        return prd_content

    async def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        LangGraph node function for the PRD Writer Agent.

        Args:
            state: Current workflow state.

        Returns:
            Updated state with prd_output populated.
        """
        user_input = state.get("user_input", "")
        decision = state.get("decision_output")
        org_context = state.get("org_memory_context", "")
        org_profile_text = state.get("org_profile_text", "") or ""

        logger.info("PRDWriterAgent: Generating PRD...")
        prd = await self.generate(user_input, decision, org_context, org_profile_text)

        return {
            **state,
            "prd_output": prd,
            "current_phase": "stress_test",
            "next_agent": "stress_test",
        }
