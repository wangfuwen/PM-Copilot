"""
Org Profile extraction and persistence.

Builds a structured organizational style profile from uploaded knowledge docs.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import settings

logger = logging.getLogger(__name__)

EMPTY_PROFILE: dict[str, Any] = {
    "document_style": {
        "structure_preference": [],
        "detail_level": "",
        "chapter_order": [],
    },
    "terminology": {
        "internal_terms": {},
        "mapping": {},
    },
    "review_focus": {
        "top_3_dimensions": [],
    },
    "lessons_learned": [],
    "success_patterns": [],
}

ORG_PROFILE_EXTRACT_PROMPT = """你是组织知识分析师。请分析以下文档集合，提取该组织的 PM 风格画像。

请只输出合法 JSON（不要 markdown 代码块），结构如下：
{
  "document_style": {
    "structure_preference": ["B端风或C端风等"],
    "detail_level": "简洁/适中/详尽",
    "chapter_order": ["常见章节顺序"]
  },
  "terminology": {
    "internal_terms": {"术语": "含义"},
    "mapping": {"通用词": "组织内部词"}
  },
  "review_focus": {
    "top_3_dimensions": ["老板/评审最关心的维度"]
  },
  "lessons_learned": ["具体踩坑经验与建议"],
  "success_patterns": ["可复用的成功写法/结构"]
}

要求：
1. 术语提取包含同义词映射
2. 踩坑经验要具体到场景和建议
3. 成功案例抽象出可复用结构
4. 文档不足时仍返回完整 JSON，未知字段用空数组/空对象
"""


def profile_path() -> Path:
    persist = Path(settings.chroma_persist_dir)
    if not persist.is_absolute():
        persist = Path.cwd() / persist
    persist.mkdir(parents=True, exist_ok=True)
    return persist / "org_profile.json"


def load_org_profile() -> dict[str, Any]:
    """Load cached Org Profile from disk."""
    path = profile_path()
    if not path.exists():
        return dict(EMPTY_PROFILE)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return dict(EMPTY_PROFILE)
        # Merge defaults for missing keys
        merged = dict(EMPTY_PROFILE)
        merged.update(data)
        return merged
    except Exception as e:
        logger.warning("Failed to load org profile: %s", e)
        return dict(EMPTY_PROFILE)


def save_org_profile(profile: dict[str, Any]) -> Path:
    """Persist Org Profile JSON to disk."""
    path = profile_path()
    path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Org profile saved to %s", path)
    return path


def format_org_profile_for_prompt(profile: Optional[dict[str, Any]] = None) -> str:
    """Format Org Profile as prompt-friendly text."""
    profile = profile if profile is not None else load_org_profile()
    if not profile or profile == EMPTY_PROFILE:
        # Treat as empty if no meaningful content
        if not any(
            [
                profile.get("terminology", {}).get("mapping"),
                profile.get("lessons_learned"),
                profile.get("success_patterns"),
                profile.get("document_style", {}).get("structure_preference"),
            ]
        ):
            return ""
    return json.dumps(profile, ensure_ascii=False, indent=2)


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if "```" in text:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            text = match.group(1).strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    # Fallback: find outermost braces
    if "{" in text and "}" in text:
        candidate = text[text.index("{") : text.rindex("}") + 1]
        data = json.loads(candidate)
        if isinstance(data, dict):
            return data
    raise ValueError("Unable to parse Org Profile JSON from model output")


async def rebuild_org_profile(samples: list[dict], llm=None) -> dict[str, Any]:
    """
    Extract Org Profile from document samples using LLM and persist it.

    Args:
        samples: List of {title, doc_type, content}
        llm: Optional chat model; defaults to org_memory routing.
    """
    if not samples:
        profile = dict(EMPTY_PROFILE)
        save_org_profile(profile)
        return profile

    if llm is None:
        llm = settings.get_llm("org_memory", temperature=0.2)

    docs_blob_parts = []
    for i, s in enumerate(samples, 1):
        docs_blob_parts.append(
            f"### 文档{i}: {s.get('title', 'Untitled')} ({s.get('doc_type', 'other')})\n"
            f"{s.get('content', '')}"
        )
    docs_blob = "\n\n".join(docs_blob_parts)

    messages = [
        SystemMessage(content=ORG_PROFILE_EXTRACT_PROMPT),
        HumanMessage(content=f"输入文档：\n\n{docs_blob[:12000]}"),
    ]

    try:
        response = await llm.ainvoke(messages)
        profile = _extract_json(response.content)
    except Exception as e:
        logger.error("Org profile extraction failed: %s", e)
        profile = dict(EMPTY_PROFILE)
        profile["lessons_learned"] = [f"Org Profile 提取失败，请重试: {e}"]

    # Normalize shape
    merged = dict(EMPTY_PROFILE)
    for key in EMPTY_PROFILE:
        if key in profile:
            merged[key] = profile[key]
    save_org_profile(merged)
    return merged
