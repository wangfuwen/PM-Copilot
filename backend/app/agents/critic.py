"""
Critic Agent — 质量审查 Agent。

Reviews PRD (or decision) outputs before stress testing.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)

CRITIC_SYSTEM_PROMPT = """你是严格的产品质量审查专家。请审查产品经理产出物，确保达到专业标准。

## 审查标准（PRD）
- 背景和目标是否清晰
- 用户画像是否具体
- 功能需求是否有优先级
- 验收标准是否可量化
- 路线图与风险是否合理

## 输出
只输出合法 JSON：
{
  "score": 7,
  "verdict": "PASS | NEEDS_REVISION | REJECT",
  "strengths": ["优点1", "优点2"],
  "improvements": ["改进1", "改进2"],
  "summary": "一句话总结"
}
score 为 1-10 整数。
"""


class CriticAgent:
    def __init__(self, llm: BaseChatModel):
        self.llm = llm

    async def review(self, content: str, content_type: str = "prd") -> dict:
        messages = [
            SystemMessage(content=CRITIC_SYSTEM_PROMPT),
            HumanMessage(content=f"请审查以下{content_type}内容：\n\n{content[:8000]}"),
        ]
        try:
            json_llm = self.llm.bind(response_format={"type": "json_object"})
            response = await json_llm.ainvoke(messages)
        except Exception:
            response = await self.llm.ainvoke(messages)

        raw = self._extract_json(response.content or "")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {
                "score": 6,
                "verdict": "NEEDS_REVISION",
                "strengths": ["已完成初稿"],
                "improvements": ["建议人工复核结构完整性"],
                "summary": raw[:300] or "审查结果解析失败",
            }

        return {
            "content_type": content_type,
            "score": data.get("score", 6),
            "verdict": data.get("verdict", "NEEDS_REVISION"),
            "strengths": data.get("strengths") or [],
            "improvements": data.get("improvements") or [],
            "summary": data.get("summary") or "",
            "review": self._format_markdown(data),
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }

    async def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        prd = state.get("prd_output") or ""
        decision = state.get("decision_output")
        content = prd if prd else json.dumps(decision or {}, ensure_ascii=False)
        content_type = "PRD" if prd else "决策分析"

        if not content.strip():
            logger.warning("CriticAgent: No content to review")
            return {**state, "critic_feedback": None}

        logger.info("CriticAgent: Reviewing %s...", content_type)
        review = await self.review(content, content_type.lower())
        return {
            **state,
            "critic_feedback": review,
            "current_phase": "review",
            "next_agent": "stress_test",
        }

    @staticmethod
    def _format_markdown(data: dict) -> str:
        score = data.get("score", "N/A")
        verdict = data.get("verdict", "N/A")
        lines = [
            f"## 质量审查\n",
            f"**评分**: {score}/10\n",
            f"**结论**: {verdict}\n",
            f"**摘要**: {data.get('summary', '')}\n",
        ]
        strengths = data.get("strengths") or []
        if strengths:
            lines.append("**优点**:")
            lines.extend([f"- {s}" for s in strengths])
            lines.append("")
        improvements = data.get("improvements") or []
        if improvements:
            lines.append("**改进建议**:")
            lines.extend([f"- {s}" for s in improvements])
        return "\n".join(lines)

    @staticmethod
    def _extract_json(text: str) -> str:
        text = (text or "").strip()
        if "```" in text:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
            if match:
                return match.group(1).strip()
        if "{" in text and "}" in text:
            return text[text.index("{") : text.rindex("}") + 1]
        return text
