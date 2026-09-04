"""
Decision Agent — 需求决策顾问。

Progressive clarify (Cursor-style):
1) Assess known vs unknown; ask ONE question with selectable options if needed
2) Repeat up to MAX_CLARIFY_STEPS, or skip / decide when enough info
3) Produce GO / PIVOT / KILL
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage, AIMessage
from langchain_core.language_models import BaseChatModel

from app.models.schemas import DecisionOutput
from app.prompts.decision import DECISION_SYSTEM_PROMPT, DECISION_USER_PROMPT
from app.config import settings
from app.telemetry import ainvoke_with_retry

logger = logging.getLogger(__name__)

CLARIFY_MARKER = "## 决策确认"
SKIP_TOKENS = (
    "__SKIP_CLARIFY__",
    "跳过，直接决策",
    "跳过直接决策",
    "跳过",
)
MAX_CLARIFY_STEPS = 3

CLARIFY_STEP_SYSTEM_PROMPT = """你是资深产品决策顾问。根据用户已提供的信息，决定下一步：
- 若做 GO/PIVOT/KILL 决策所需的关键信息已足够 → action=decide
- 若仍有 1 个关键不确定点 → action=ask，只问这一件事

硬性规则：
1. 每轮最多问 1 个问题；问题要短（一句话）
2. 只问用户尚未说清、且会影响决策的点；已明确的内容禁止再问
3. 不要问卷式盘问，不要解释「为什么问」，不要写长 intro
4. 提供 2–4 个具体、互斥、贴合上下文的选项（短标签）
5. 不要把「跳过」放进 options（系统会自动加）
6. 若信息已经够用，宁可 decide，也不要为了凑问题而问

只输出合法 JSON，二选一：

A) 需要追问：
{
  "action": "ask",
  "id": "short_snake_id",
  "question": "一句话问题",
  "options": [
    {"id": "opt_a", "label": "选项文案"},
    {"id": "opt_b", "label": "选项文案"}
  ],
  "hint": "可选，极短提示（可省略）"
}

B) 可以决策：
{
  "action": "decide",
  "reason": "一句话说明为何已够"
}
"""


class DecisionAgent:
    """Decision Agent with progressive clarify-then-decide flow."""

    def __init__(self, llm: BaseChatModel):
        self.llm = llm

    async def next_clarify_step(
        self,
        user_requirement: str,
        qa_so_far: list[dict[str, str]],
        org_memory_context: str = "",
        step: int = 1,
    ) -> dict:
        """Ask LLM for one clarify step or decide."""
        qa_text = self._format_qa(qa_so_far)
        org_block = (
            f"\n组织记忆参考（仅供判断缺口，勿复述）：\n{org_memory_context[:1200]}"
            if org_memory_context
            else ""
        )
        human = (
            f"原始需求：\n{user_requirement}\n\n"
            f"已确认信息（Q&A）：\n{qa_text or '（暂无）'}\n\n"
            f"当前是第 {step}/{MAX_CLARIFY_STEPS} 轮追问。"
            f"{org_block}\n\n"
            "请输出 JSON。"
        )
        messages = [
            SystemMessage(content=CLARIFY_STEP_SYSTEM_PROMPT),
            HumanMessage(content=human),
        ]
        data = await self._invoke_json(messages)
        return self._normalize_step(data, step)

    async def analyze(
        self,
        user_requirement: str,
        org_memory_context: str = "",
        org_profile_text: str = "",
        conversation_context: str = "",
    ) -> DecisionOutput:
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
        if conversation_context:
            user_prompt += f"\n\n## 追问与用户补充信息\n{conversation_context}"

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        content = await self._invoke_text(messages)
        content = self._extract_json(content)

        try:
            decision = DecisionOutput.model_validate_json(content)
        except Exception as e:
            logger.warning("Failed to parse decision output: %s, using fallback", e)
            decision = DecisionOutput(
                five_w_one_h={"what": user_requirement},
                recommendation="PIVOT",
                reasoning=content if content else "无法解析决策输出，建议人工复核。",
                risks=["解析失败，需要人工审核"],
                confidence=0.3,
            )
        return decision

    async def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        user_input = state.get("user_input", "") or ""
        org_context = state.get("org_memory_context", "") or ""
        org_profile_text = state.get("org_profile_text", "") or ""
        messages = state.get("messages") or []
        skip_clarify = bool(state.get("skip_clarify"))
        enable_clarify = settings.enable_decision_clarify and not skip_clarify

        original_requirement = self._extract_original_requirement(messages, user_input)
        qa_pairs = self._extract_qa_pairs(messages)
        answered_steps = len(qa_pairs)
        user_skipped = self._is_skip_answer(user_input)

        should_decide = (
            not enable_clarify
            or user_skipped
            or answered_steps >= MAX_CLARIFY_STEPS
        )

        if enable_clarify and not should_decide:
            pending = self._last_unanswered_clarify(messages)
            if pending:
                # Client re-ran without a new answer — re-surface the same step
                logger.info("DecisionAgent: re-emitting unanswered clarify step")
                return {
                    **state,
                    "clarifying_questions": pending,
                    "awaiting_clarification": True,
                    "decision_output": None,
                    "current_phase": "clarify",
                    "next_agent": "__end__",
                }

            next_step = answered_steps + 1
            logger.info(
                "DecisionAgent: progressive clarify step %s/%s",
                next_step,
                MAX_CLARIFY_STEPS,
            )
            step_result = await self.next_clarify_step(
                original_requirement,
                qa_pairs,
                org_context,
                step=next_step,
            )
            if step_result.get("action") == "ask":
                clarify = {
                    "mode": "clarify_step",
                    "step": next_step,
                    "max_steps": MAX_CLARIFY_STEPS,
                    "id": step_result.get("id") or f"step_{next_step}",
                    "question": step_result["question"],
                    "options": step_result["options"],
                    "allow_custom": True,
                    "hint": step_result.get("hint") or "",
                }
                return {
                    **state,
                    "clarifying_questions": clarify,
                    "awaiting_clarification": True,
                    "decision_output": None,
                    "current_phase": "clarify",
                    "next_agent": "__end__",
                }
            logger.info(
                "DecisionAgent: LLM ready to decide (%s)",
                step_result.get("reason"),
            )

        logger.info("DecisionAgent: Analyzing requirement...")
        conversation_context = self._extract_clarify_context(
            messages, user_input, original_requirement
        )
        decision = await self.analyze(
            original_requirement,
            org_context,
            org_profile_text,
            conversation_context=conversation_context,
        )
        logger.info("DecisionAgent: Recommendation = %s", decision.recommendation)

        return {
            **state,
            "decision_output": decision.model_dump(),
            "clarifying_questions": None,
            "awaiting_clarification": False,
            "current_phase": "prd_generation",
            "next_agent": "prd_writer",
        }

    # ──────────────────────────────────────────────
    # History helpers
    # ──────────────────────────────────────────────

    @staticmethod
    def _is_skip_answer(text: str) -> bool:
        t = (text or "").strip()
        if not t:
            return False
        if t in SKIP_TOKENS:
            return True
        # option chip may send exact skip label
        return t.replace(" ", "") in {s.replace(" ", "") for s in SKIP_TOKENS}

    @staticmethod
    def _parse_clarify_payload(content: str) -> dict | None:
        """Parse structured clarify block from assistant message."""
        if not content or CLARIFY_MARKER not in content:
            return None
        # Prefer fenced JSON after marker
        match = re.search(
            r"```json\s*(\{.*?\})\s*```",
            content,
            re.DOTALL,
        )
        if match:
            try:
                data = json.loads(match.group(1))
                if isinstance(data, dict) and data.get("question"):
                    return data
            except json.JSONDecodeError:
                pass
        # Fallback: first JSON object in message
        if "{" in content and "}" in content:
            try:
                candidate = content[content.index("{") : content.rindex("}") + 1]
                data = json.loads(candidate)
                if isinstance(data, dict) and data.get("question"):
                    return data
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    @classmethod
    def _extract_qa_pairs(cls, messages: list[BaseMessage]) -> list[dict[str, str]]:
        """Build answered Q&A pairs from clarify markers + following human replies."""
        pairs: list[dict[str, str]] = []
        i = 0
        while i < len(messages):
            msg = messages[i]
            if isinstance(msg, AIMessage) and CLARIFY_MARKER in (msg.content or ""):
                payload = cls._parse_clarify_payload(msg.content or "")
                question = (payload or {}).get("question") or "（追问）"
                # Find next human answer
                answer = None
                for j in range(i + 1, len(messages)):
                    if isinstance(messages[j], HumanMessage):
                        answer = (messages[j].content or "").strip()
                        break
                    if isinstance(messages[j], AIMessage) and CLARIFY_MARKER in (
                        messages[j].content or ""
                    ):
                        break
                if answer and not cls._is_skip_answer(answer):
                    pairs.append({"question": question, "answer": answer})
            i += 1
        return pairs

    @classmethod
    def _last_unanswered_clarify(cls, messages: list[BaseMessage]) -> dict | None:
        """If last clarify has no human reply, return its payload for re-emit."""
        last_clarify = -1
        last_payload: dict | None = None
        for i, msg in enumerate(messages):
            if isinstance(msg, AIMessage) and CLARIFY_MARKER in (msg.content or ""):
                last_clarify = i
                last_payload = cls._parse_clarify_payload(msg.content or "")
        if last_clarify < 0 or not last_payload:
            return None
        for msg in messages[last_clarify + 1 :]:
            if isinstance(msg, HumanMessage) and (msg.content or "").strip():
                return None
        # Ensure shape for frontend
        last_payload.setdefault("mode", "clarify_step")
        last_payload.setdefault("allow_custom", True)
        last_payload.setdefault("max_steps", MAX_CLARIFY_STEPS)
        return last_payload

    @staticmethod
    def _extract_original_requirement(
        messages: list[BaseMessage], fallback: str
    ) -> str:
        """First substantial user message before any clarify, else fallback."""
        for msg in messages:
            if isinstance(msg, HumanMessage):
                text = (msg.content or "").strip()
                if text and text not in SKIP_TOKENS:
                    return text
            if isinstance(msg, AIMessage) and CLARIFY_MARKER in (msg.content or ""):
                break
        return fallback

    @staticmethod
    def _format_qa(qa: list[dict[str, str]]) -> str:
        if not qa:
            return ""
        lines = []
        for i, item in enumerate(qa, 1):
            lines.append(f"{i}. Q: {item.get('question', '')}")
            lines.append(f"   A: {item.get('answer', '')}")
        return "\n".join(lines)

    @classmethod
    def _extract_clarify_context(
        cls,
        messages: list[BaseMessage],
        latest_user: str,
        original_requirement: str,
    ) -> str:
        parts = [f"原始需求：\n{original_requirement}"]
        qa = cls._extract_qa_pairs(messages)
        if qa:
            parts.append("已确认：\n" + cls._format_qa(qa))
        if latest_user and not cls._is_skip_answer(latest_user):
            # Include latest if not already last QA answer
            if not qa or qa[-1].get("answer") != latest_user.strip():
                # Avoid duplicating original requirement
                if latest_user.strip() != original_requirement.strip():
                    parts.append(f"用户最新补充：\n{latest_user}")
        if cls._is_skip_answer(latest_user):
            parts.append("用户选择跳过剩余追问，请基于已有信息决策。")
        return "\n\n".join(parts)

    @staticmethod
    def _normalize_step(data: dict, step: int) -> dict:
        action = (data.get("action") or "").strip().lower()
        if action == "decide":
            return {
                "action": "decide",
                "reason": data.get("reason") or "信息已足够",
            }

        question = (data.get("question") or "").strip()
        raw_opts = data.get("options") or []
        options: list[dict[str, str]] = []
        for i, opt in enumerate(raw_opts):
            if isinstance(opt, dict):
                label = (opt.get("label") or "").strip()
                oid = (opt.get("id") or f"opt_{i}").strip()
            else:
                label = str(opt).strip()
                oid = f"opt_{i}"
            if label and oid != "skip" and "跳过" not in label:
                options.append({"id": oid, "label": label})
        options = options[:4]

        if not question or len(options) < 2:
            # Fallback: gentle single question if model failed
            return {
                "action": "ask",
                "id": data.get("id") or f"step_{step}",
                "question": question or "这个想法最核心要解决的痛点是什么？",
                "options": options
                or [
                    {"id": "pain_clear", "label": "已有明确高频痛点"},
                    {"id": "pain_explore", "label": "还在探索，痛点不清晰"},
                    {"id": "pain_nice", "label": "偏锦上添花，不是刚需"},
                ],
                "hint": (data.get("hint") or "").strip(),
            }

        return {
            "action": "ask",
            "id": data.get("id") or f"step_{step}",
            "question": question,
            "options": options,
            "hint": (data.get("hint") or "").strip(),
        }

    async def _invoke_json(self, messages: list) -> dict:
        text = await self._invoke_text(messages)
        text = self._extract_json(text)
        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    async def _invoke_text(self, messages: list) -> str:
        try:
            json_llm = self.llm.bind(response_format={"type": "json_object"})
            response = await ainvoke_with_retry(
                json_llm, messages, max_retries=2, agent="decision"
            )
        except Exception:
            response = await ainvoke_with_retry(
                self.llm, messages, max_retries=2, agent="decision"
            )
        return response.content or ""

    @staticmethod
    def _extract_json(text: str) -> str:
        text = (text or "").strip()
        for marker in ["```json", "```"]:
            if marker in text:
                start = text.index(marker) + len(marker)
                end = text.index("```", start)
                candidate = text[start:end].strip()
                if candidate.startswith("{"):
                    return candidate

        match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
        if match:
            candidate = match.group(0).strip()
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                pass

        if "{" in text and "}" in text:
            start = text.index("{")
            end = text.rindex("}") + 1
            candidate = text[start:end].strip()
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                pass
        return text


def format_clarify_step(clarify: dict) -> str:
    """Render one clarify step for chat history (machine-readable + readable)."""
    step = clarify.get("step", 1)
    max_steps = clarify.get("max_steps", MAX_CLARIFY_STEPS)
    question = clarify.get("question") or ""
    hint = (clarify.get("hint") or "").strip()

    payload = {
        "mode": "clarify_step",
        "step": step,
        "max_steps": max_steps,
        "id": clarify.get("id") or f"step_{step}",
        "question": question,
        "options": clarify.get("options") or [],
        "allow_custom": bool(clarify.get("allow_custom", True)),
        "hint": hint,
    }

    lines = [
        CLARIFY_MARKER,
        "",
        f"**确认 ({step}/{max_steps})**",
        "",
        question,
    ]
    if hint:
        lines.extend(["", f"_{hint}_"])
    lines.extend(
        [
            "",
            "```json",
            json.dumps(payload, ensure_ascii=False),
            "```",
        ]
    )
    return "\n".join(lines)


# Back-compat alias used by older imports
def format_clarifying_questions(clarify: dict) -> str:
    if clarify.get("mode") == "clarify_step" or clarify.get("question"):
        return format_clarify_step(clarify)
    # Legacy batch format (should not be used)
    intro = clarify.get("intro") or ""
    lines = [CLARIFY_MARKER, "", intro, ""]
    for i, q in enumerate(clarify.get("questions") or [], 1):
        question = q.get("question") if isinstance(q, dict) else str(q)
        lines.append(f"{i}. **{question}**")
    return "\n".join(lines)
