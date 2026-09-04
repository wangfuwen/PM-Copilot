"""
Evaluation Agent — 对决策 / PRD 做结构化自动评分。
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.language_models import BaseChatModel

from app.telemetry import ainvoke_with_retry

logger = logging.getLogger(__name__)

EVAL_SYSTEM_PROMPT = """你是产品评审官，负责对「决策报告」或「PRD」做客观打分。
对照用户原始需求与已确认信息，从以下维度打分（每项 0–10 整数）：

1. completeness（完整性）：关键信息是否齐全
2. consistency（一致性）：内部逻辑是否自洽、无矛盾
3. requirement_fit（需求契合度）：是否真正回应了用户需求
4. clarity（清晰度）：表述是否清楚、可执行
5. actionability（可落地性）：下一步是否明确可执行

只输出合法 JSON：
{
  "target": "decision | prd",
  "scores": {
    "completeness": 8,
    "consistency": 7,
    "requirement_fit": 8,
    "clarity": 7,
    "actionability": 6
  },
  "overall": 7.2,
  "verdict": "STRONG | ADEQUATE | WEAK",
  "highlights": ["优点1"],
  "gaps": ["缺口1"],
  "summary": "一句话总评"
}

overall 为五维平均分（保留 1 位小数）。verdict：overall≥8 STRONG；≥6 ADEQUATE；否则 WEAK。
"""


class EvaluatorAgent:
    def __init__(self, llm: BaseChatModel):
        self.llm = llm

    async def evaluate(
        self,
        content: str,
        *,
        target: str,
        user_requirement: str = "",
        clarify_context: str = "",
    ) -> dict:
        context_parts = []
        if user_requirement:
            context_parts.append(f"## 用户原始需求\n{user_requirement}")
        if clarify_context:
            context_parts.append(f"## 已确认补充\n{clarify_context}")
        context_parts.append(f"## 待评估内容（{target}）\n{content[:8000]}")

        messages = [
            SystemMessage(content=EVAL_SYSTEM_PROMPT),
            HumanMessage(content="\n\n".join(context_parts)),
        ]

        try:
            json_llm = self.llm.bind(response_format={"type": "json_object"})
            response = await ainvoke_with_retry(
                json_llm, messages, max_retries=2, agent="evaluator"
            )
        except Exception:
            response = await ainvoke_with_retry(
                self.llm, messages, max_retries=2, agent="evaluator"
            )

        raw = self._extract_json(getattr(response, "content", None) or "")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {}

        scores = data.get("scores") or {}
        dims = [
            "completeness",
            "consistency",
            "requirement_fit",
            "clarity",
            "actionability",
        ]
        normalized = {}
        for d in dims:
            try:
                normalized[d] = max(0, min(10, int(scores.get(d, 6))))
            except (TypeError, ValueError):
                normalized[d] = 6

        overall = data.get("overall")
        try:
            overall = round(float(overall), 1)
        except (TypeError, ValueError):
            overall = round(sum(normalized.values()) / len(normalized), 1)

        if overall >= 8:
            verdict = "STRONG"
        elif overall >= 6:
            verdict = "ADEQUATE"
        else:
            verdict = "WEAK"
        if data.get("verdict") in ("STRONG", "ADEQUATE", "WEAK"):
            verdict = data["verdict"]

        result = {
            "target": target if target in ("decision", "prd") else "decision",
            "scores": normalized,
            "overall": overall,
            "verdict": verdict,
            "highlights": data.get("highlights") or [],
            "gaps": data.get("gaps") or [],
            "summary": data.get("summary") or "",
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }
        result["report"] = self._format_markdown(result)
        return result

    async def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        prd = state.get("prd_output") or ""
        decision = state.get("decision_output")
        user_requirement = state.get("user_input") or ""

        if prd.strip():
            target = "prd"
            content = prd
        elif decision:
            target = "decision"
            content = json.dumps(decision, ensure_ascii=False, indent=2)
        else:
            logger.warning("EvaluatorAgent: nothing to evaluate")
            return {**state, "evaluation": None}

        # Light clarify context from recent messages
        clarify_bits = []
        for msg in state.get("messages") or []:
            content_msg = getattr(msg, "content", "") or ""
            if "## 决策确认" in content_msg or "用户回答" in content_msg:
                clarify_bits.append(content_msg[:500])
        clarify_context = "\n".join(clarify_bits[-4:])

        logger.info("EvaluatorAgent: evaluating %s", target)
        evaluation = await self.evaluate(
            content,
            target=target,
            user_requirement=user_requirement,
            clarify_context=clarify_context,
        )
        return {
            **state,
            "evaluation": evaluation,
            "current_phase": "review",
        }

    @staticmethod
    def _format_markdown(data: dict) -> str:
        labels = {
            "completeness": "完整性",
            "consistency": "一致性",
            "requirement_fit": "需求契合",
            "clarity": "清晰度",
            "actionability": "可落地性",
        }
        target = "PRD" if data.get("target") == "prd" else "决策"
        lines = [
            f"## Evaluation · {target}",
            "",
            f"**综合分**: {data.get('overall')}/10 · **结论**: {data.get('verdict')}",
            "",
        ]
        if data.get("summary"):
            lines.append(f"{data['summary']}\n")
        lines.append("**分项得分**:")
        for key, label in labels.items():
            score = (data.get("scores") or {}).get(key, "-")
            lines.append(f"- {label}: {score}/10")
        highlights = data.get("highlights") or []
        if highlights:
            lines.append("\n**亮点**:")
            lines.extend([f"- {h}" for h in highlights])
        gaps = data.get("gaps") or []
        if gaps:
            lines.append("\n**缺口**:")
            lines.extend([f"- {g}" for g in gaps])
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
