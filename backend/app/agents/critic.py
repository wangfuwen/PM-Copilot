"""
Critic Agent — 质量审查 Agent (v0.2)。

Reviews outputs from other agents for quality, completeness, and consistency.
Acts as a final quality gate before delivering results to the user.
"""

import logging
from typing import Any

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)

CRITIC_SYSTEM_PROMPT = """\
你是一位严格的产品质量审查专家。你的职责是审查产品经理的产出物（PRD、决策分析等），确保其达到专业标准。

## 审查标准

### PRD 审查
- [ ] 背景和目标是否清晰？
- [ ] 用户画像是否具体？
- [ ] 功能需求是否有优先级划分？
- [ ] 验收标准是否可量化？
- [ ] 路线图是否合理？
- [ ] 非功能需求是否覆盖？

### 决策分析审查
- [ ] 5W1H 是否完整？
- [ ] 决策理由是否充分？
- [ ] 风险评估是否全面？
- [ ] 是否考虑了替代方案？

## 输出格式

请输出：
1. **总体评分** (1-10)
2. **优点** (至少 2 条)
3. **改进建议** (至少 2 条，按优先级排序)
4. **审查结论**: PASS / NEEDS_REVISION / REJECT
"""


class CriticAgent:
    """
    Critic Agent that reviews outputs from other agents for quality assurance.

    Provides structured feedback on:
    - Completeness of analysis
    - Clarity and actionability of recommendations
    - Consistency across documents
    - Professional quality standards

    Note: This agent is designed for v0.2 integration into the workflow.

    Attributes:
        llm: The language model used for review.
    """

    def __init__(self, llm: BaseChatModel):
        """
        Initialize the Critic Agent.

        Args:
            llm: A LangChain chat model instance.
        """
        self.llm = llm

    async def review(self, content: str, content_type: str = "prd") -> dict:
        """
        Review the given content for quality.

        Args:
            content: The content to review (PRD, decision output, etc.).
            content_type: Type of content for context-specific review criteria.

        Returns:
            Review results with score, strengths, improvements, and verdict.
        """
        messages = [
            SystemMessage(content=CRITIC_SYSTEM_PROMPT),
            HumanMessage(content=f"请审查以下{content_type}内容：\n\n{content}"),
        ]

        response = await self.llm.ainvoke(messages)
        review_text = response.content

        return {
            "content_type": content_type,
            "review": review_text,
            "reviewed_at": None,  # Will be set by the workflow
        }

    async def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        LangGraph node function for the Critic Agent.

        Args:
            state: Current workflow state.

        Returns:
            Updated state with critic feedback.
        """
        # Determine what to review
        prd = state.get("prd_output", "")
        decision = state.get("decision_output")

        content = prd if prd else str(decision)
        content_type = "PRD" if prd else "决策分析"

        if not content:
            logger.warning("CriticAgent: No content to review")
            return state

        logger.info(f"CriticAgent: Reviewing {content_type}...")
        review = await self.review(content, content_type.lower())
        logger.info("CriticAgent: Review complete")

        return {
            **state,
            "critic_feedback": review,
        }
