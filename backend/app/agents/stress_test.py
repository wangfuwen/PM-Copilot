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
    ) -> list[StressTestChallenge]:
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

        from app.telemetry import ainvoke_with_retry

        response = await ainvoke_with_retry(
            self.llm, messages, max_retries=2, agent="stress_test"
        )
        content = response.content or ""

        # Parse response into structured challenge
        try:
            parsed = self._parse_challenge_response(content, role)
            return parsed
        except Exception as e:
            logger.warning(f"Failed to parse challenge for role {role}: {e}")
            return [
                StressTestChallenge(
                    role=ROLE_NAMES.get(role, role),
                    challenge=content[:500] or "该角色返回了无法解析的结果",
                    severity="medium",
                    suggestions=["建议人工复核此角色的挑战结果"],
                )
            ]

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
        role_results = await asyncio.gather(*tasks, return_exceptions=True)
        challenges: list[StressTestChallenge] = []
        failed_roles: list[str] = []
        for role, result in zip(roles, role_results):
            if isinstance(result, Exception):
                logger.error("Stress role %s failed: %s", role, result)
                failed_roles.append(ROLE_NAMES.get(role, role))
                continue
            challenges.extend(result)

        challenges = self._dedupe_challenges(challenges)

        # Calculate overall score based on severity
        severity_scores = {"low": 90, "medium": 70, "high": 50, "critical": 30}
        if challenges:
            avg_score = sum(
                severity_scores.get(c.severity, 50) for c in challenges
            ) / len(challenges)
        else:
            avg_score = 0 if failed_roles else 100

        severity_counts = {
            severity: sum(1 for c in challenges if c.severity == severity)
            for severity in ("critical", "high", "medium", "low")
        }
        summary_parts = [
            f"共发现 {len(challenges)} 个问题",
            "，".join(f"{level}: {count}" for level, count in severity_counts.items()),
        ]
        if failed_roles:
            summary_parts.append(f"未完成角色：{'、'.join(failed_roles)}")
        summary = "\n".join(summary_parts)

        return StressTestOutput(
            challenges=list(challenges),
            overall_score=round(avg_score, 1),
            summary=summary,
            failed_roles=failed_roles,
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
                "stress_test_summary": {
                    "overall_score": None,
                    "summary": "missing_prd",
                    "missing_prd": True,
                },
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
                "issue_count": len(results.challenges),
                "failed_roles": results.failed_roles,
            },
            "current_phase": "complete",
            "next_agent": "__end__",
        }

    @staticmethod
    def _parse_challenge_response(content: str, role: str) -> list[StressTestChallenge]:
        """Parse every structured issue returned by one review role."""
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
            try:
                data = json.loads(content.strip())
            except json.JSONDecodeError:
                # Fallback: treat unstructured prose as a single challenge.
                return [
                    StressTestChallenge(
                        role=ROLE_NAMES.get(role, role),
                        challenge=content[:800],
                        severity="medium",
                        suggestions=["建议进一步优化方案以应对此挑战"],
                    )
                ]

        # Handle nested structure
        if isinstance(data, dict):
            items = data.get("challenges", [data])
            if not isinstance(items, list):
                items = [items]
            parsed: list[StressTestChallenge] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                challenge = str(item.get("challenge") or "").strip()
                if not challenge:
                    continue
                severity = str(item.get("severity") or "medium").lower()
                if severity not in {"low", "medium", "high", "critical"}:
                    severity = "medium"
                suggestions = item.get("suggestions") or []
                if not isinstance(suggestions, list):
                    suggestions = [str(suggestions)]
                parsed.append(
                    StressTestChallenge(
                        role=ROLE_NAMES.get(role, data.get("role", role)),
                        challenge=challenge,
                        severity=severity,
                        suggestions=[str(s) for s in suggestions if str(s).strip()],
                    )
                )
            if parsed:
                return parsed

        return [
            StressTestChallenge(
                role=ROLE_NAMES.get(role, role),
                challenge=content[:800],
                severity="medium",
            )
        ]

    @staticmethod
    def _dedupe_challenges(
        challenges: list[StressTestChallenge],
    ) -> list[StressTestChallenge]:
        seen: set[str] = set()
        unique: list[StressTestChallenge] = []
        for challenge in challenges:
            key = "".join(challenge.challenge.lower().split())
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(challenge)
        return unique
