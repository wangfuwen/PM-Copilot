"""
Stress Test Lead Agent — 红队压力测试。

Challenges PRDs from 5 different role perspectives:
Boss (ROI), Engineer (feasibility), User (need validation),
Competitor (differentiation), Compliance (risk).
"""

import json
import asyncio
import logging
from typing import Any

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.language_models import BaseChatModel

from app.models.schemas import StressTestChallenge, StressTestOutput
from app.prompts.stress_test import STRESS_TEST_SYSTEM_PROMPT, ROLE_PROMPTS

logger = logging.getLogger(__name__)

# Role display names
ROLE_NAMES = {
    "boss": "👔 老板/投资人",
    "engineer": "👨‍💻 技术负责人",
    "user": "👤 真实用户",
    "competitor": "🏢 竞品分析师",
    "compliance": "⚖️ 合规/风控专家",
}


class StressTestAgent:
    """
    Stress Test Lead that challenges PRDs from 5 critical role perspectives.

    Executes parallel challenges from:
    1. Boss/Investor — ROI and resource allocation scrutiny
    2. Tech Lead — Technical feasibility and architecture impact
    3. Real User — Pain point validation and usability
    4. Competitor Analyst — Differentiation and market positioning
    5. Compliance Expert — Legal, data security, and brand risks

    Attributes:
        llm: The language model used for challenges.
    """

    def __init__(self, llm: BaseChatModel):
        """
        Initialize the Stress Test Agent.

        Args:
            llm: A LangChain chat model instance.
        """
        self.llm = llm

    async def _challenge_from_role(
        self,
        role: str,
        prd_content: str,
        org_history: str = "",
    ) -> StressTestChallenge:
        """
        Run a challenge from a single role perspective.

        Args:
            role: Role key (boss, engineer, user, competitor, compliance).
            prd_content: The PRD document to challenge.
            org_history: Optional organizational history lessons for prompts.

        Returns:
            StressTestChallenge with role-specific findings.
        """
        history_block = ""
        if org_history:
            history_block = (
                "\n\n## 组织历史经验（额外评审视角）\n"
                f"{org_history}\n"
                "请在挑战中适当引用历史踩坑（如有），并给出可操作建议。"
            )

        system_prompt = STRESS_TEST_SYSTEM_PROMPT.replace("{org_history}", history_block)
        # Use replace() so braces in PRD content don't break str.format()
        role_prompt = ROLE_PROMPTS[role].replace("{prd_content}", prd_content)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=role_prompt),
        ]

        response = await self.llm.ainvoke(messages)
        content = response.content

        # Parse response into structured challenge
        try:
            parsed = self._parse_challenge_response(content, role)
            return parsed
        except Exception as e:
            logger.warning(f"Failed to parse challenge for role {role}: {e}")
            return StressTestChallenge(
                role=ROLE_NAMES.get(role, role),
                challenge=content[:500],
                severity="medium",
                suggestions=["建议人工复核此角色的挑战结果"],
            )

    async def run_stress_test(
        self,
        prd_content: str,
        org_history: str = "",
    ) -> StressTestOutput:
        """
        Run the full stress test: challenge PRD from all 5 roles in parallel.

        Args:
            prd_content: The PRD document to stress test.
            org_history: Optional organizational history lessons.

        Returns:
            StressTestOutput with challenges from all roles.
        """
        roles = list(ROLE_PROMPTS.keys())

        # Execute all role challenges in parallel for speed
        tasks = [
            self._challenge_from_role(role, prd_content, org_history) for role in roles
        ]
        challenges = list(await asyncio.gather(*tasks))

        # Optional 6th perspective: organizational history
        if org_history:
            challenges.append(
                StressTestChallenge(
                    role="🧠 组织历史视角",
                    challenge=(
                        "基于组织记忆中的历史复盘/踩坑记录，请重点关注与当前方案相似的失败模式。"
                        f"\n\n参考材料：\n{org_history[:1200]}"
                    ),
                    severity="high",
                    suggestions=[
                        "对照历史复盘检查是否重复踩坑",
                        "在 PRD 风险章节补充组织历史案例引用",
                    ],
                )
            )

        # Calculate overall score based on severity
        severity_scores = {"low": 90, "medium": 70, "high": 50, "critical": 30}
        avg_score = sum(
            severity_scores.get(c.severity, 50) for c in challenges
        ) / len(challenges)

        summary_parts = [f"【{c.role}】严重度: {c.severity}" for c in challenges]
        summary = "\n".join(summary_parts)

        return StressTestOutput(
            challenges=list(challenges),
            overall_score=round(avg_score, 1),
            summary=summary,
        )

    async def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        LangGraph node function for the Stress Test Agent.

        Args:
            state: Current workflow state.

        Returns:
            Updated state with stress_test_results populated.
        """
        prd_content = state.get("prd_output", "")
        if not prd_content:
            logger.warning("StressTestAgent: No PRD content to test")
            return {
                **state,
                "stress_test_results": [],
                "current_phase": "complete",
                "next_agent": "__end__",
            }

        org_history = state.get("org_history_context") or state.get("org_memory_context") or ""
        logger.info("StressTestAgent: Running stress test from 5 roles...")
        results = await self.run_stress_test(prd_content, org_history=org_history)
        logger.info(f"StressTestAgent: Overall score = {results.overall_score}")

        return {
            **state,
            "stress_test_results": [c.model_dump() for c in results.challenges],
            "stress_test_summary": {
                "overall_score": results.overall_score,
                "summary": results.summary,
            },
            "current_phase": "complete",
            "next_agent": "__end__",
        }

    @staticmethod
    def _parse_challenge_response(content: str, role: str) -> StressTestChallenge:
        """Parse LLM response into a StressTestChallenge object."""
        # Try to extract JSON
        if "```json" in content:
            start = content.index("```json") + 7
            end = content.index("```", start)
            json_str = content[start:end].strip()
            data = json.loads(json_str)
        elif "```" in content:
            start = content.index("```") + 3
            end = content.index("```", start)
            json_str = content[start:end].strip()
            data = json.loads(json_str)
        else:
            # Fallback: treat entire content as the challenge
            return StressTestChallenge(
                role=ROLE_NAMES.get(role, role),
                challenge=content[:800],
                severity="medium",
                suggestions=["建议进一步优化方案以应对此挑战"],
            )

        # Handle nested structure
        if isinstance(data, dict):
            challenges = data.get("challenges", [data])
            if challenges:
                first = challenges[0] if isinstance(challenges, list) else challenges
                return StressTestChallenge(
                    role=ROLE_NAMES.get(role, data.get("role", role)),
                    challenge=first.get("challenge", str(first)),
                    severity=first.get("severity", "medium"),
                    suggestions=first.get("suggestions", []),
                )

        return StressTestChallenge(
            role=ROLE_NAMES.get(role, role),
            challenge=content[:800],
            severity="medium",
        )
