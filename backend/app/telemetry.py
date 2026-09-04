"""
Agent execution telemetry: duration, token usage, retries.
"""

from __future__ import annotations

import logging
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

_current_node: ContextVar[Optional[str]] = ContextVar("telemetry_node", default=None)
_tracker: ContextVar[Optional["RunTelemetry"]] = ContextVar("telemetry_tracker", default=None)


@dataclass
class NodeMetrics:
    agent: str
    duration_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    retry_count: int = 0
    attempts: int = 1
    error: Optional[str] = None
    status: str = "completed"  # completed | failed | skipped

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "duration_ms": self.duration_ms,
            "tokens": {
                "prompt": self.prompt_tokens,
                "completion": self.completion_tokens,
                "total": self.total_tokens,
            },
            "retry_count": self.retry_count,
            "attempts": self.attempts,
            "error": self.error,
            "status": self.status,
        }


@dataclass
class RunTelemetry:
    nodes: dict[str, NodeMetrics] = field(default_factory=dict)
    _starts: dict[str, float] = field(default_factory=dict)

    def begin(self, agent: str) -> None:
        self._starts[agent] = time.perf_counter()
        if agent not in self.nodes:
            self.nodes[agent] = NodeMetrics(agent=agent)
        _current_node.set(agent)

    def end(self, agent: str, *, error: Optional[str] = None, skipped: bool = False) -> NodeMetrics:
        started = self._starts.pop(agent, None)
        m = self.nodes.setdefault(agent, NodeMetrics(agent=agent))
        if started is not None:
            m.duration_ms = max(0, int((time.perf_counter() - started) * 1000))
        if skipped:
            m.status = "skipped"
        elif error:
            m.status = "failed"
            m.error = error
        else:
            m.status = "completed"
        _current_node.set(None)
        return m

    def add_usage(
        self,
        prompt: int = 0,
        completion: int = 0,
        total: int = 0,
        agent: Optional[str] = None,
    ) -> None:
        name = agent or _current_node.get()
        if not name:
            return
        m = self.nodes.setdefault(name, NodeMetrics(agent=name))
        m.prompt_tokens += int(prompt or 0)
        m.completion_tokens += int(completion or 0)
        if total:
            m.total_tokens += int(total)
        else:
            m.total_tokens = m.prompt_tokens + m.completion_tokens

    def add_retry(self, agent: Optional[str] = None) -> None:
        name = agent or _current_node.get()
        if not name:
            return
        m = self.nodes.setdefault(name, NodeMetrics(agent=name))
        m.retry_count += 1
        m.attempts += 1


def get_tracker() -> Optional[RunTelemetry]:
    return _tracker.get()


def set_tracker(tracker: Optional[RunTelemetry]) -> None:
    _tracker.set(tracker)


def extract_usage(response: Any) -> dict[str, int]:
    """Best-effort token usage from LangChain AIMessage / response."""
    usage = {"prompt": 0, "completion": 0, "total": 0}
    if response is None:
        return usage

    meta = getattr(response, "usage_metadata", None) or {}
    if isinstance(meta, dict) and meta:
        usage["prompt"] = int(meta.get("input_tokens") or meta.get("prompt_tokens") or 0)
        usage["completion"] = int(
            meta.get("output_tokens") or meta.get("completion_tokens") or 0
        )
        usage["total"] = int(meta.get("total_tokens") or (usage["prompt"] + usage["completion"]))
        return usage

    resp_meta = getattr(response, "response_metadata", None) or {}
    token_usage = resp_meta.get("token_usage") or resp_meta.get("usage") or {}
    if isinstance(token_usage, dict):
        usage["prompt"] = int(token_usage.get("prompt_tokens") or token_usage.get("input_tokens") or 0)
        usage["completion"] = int(
            token_usage.get("completion_tokens") or token_usage.get("output_tokens") or 0
        )
        usage["total"] = int(
            token_usage.get("total_tokens") or (usage["prompt"] + usage["completion"])
        )
    return usage


async def ainvoke_with_retry(
    llm,
    messages: list,
    *,
    max_retries: int = 2,
    agent: Optional[str] = None,
):
    """
    Invoke LLM with retries. Records token usage + retry_count on the active tracker.
    """
    tracker = get_tracker()
    last_err: Optional[Exception] = None
    attempts = max(1, max_retries + 1)

    for attempt in range(attempts):
        try:
            response = await llm.ainvoke(messages)
            usage = extract_usage(response)
            if tracker:
                tracker.add_usage(
                    prompt=usage["prompt"],
                    completion=usage["completion"],
                    total=usage["total"],
                    agent=agent,
                )
            return response
        except Exception as e:
            last_err = e
            logger.warning(
                "LLM invoke failed (attempt %s/%s): %s: %s",
                attempt + 1,
                attempts,
                type(e).__name__,
                e,
            )
            if attempt < attempts - 1:
                if tracker:
                    tracker.add_retry(agent=agent)
                continue
            raise

    raise last_err or RuntimeError("LLM invoke failed")
