"""
Memory Retriever — 检索器封装。

Provides a higher-level retrieval interface that combines
vector search with result formatting and filtering.
"""

import logging
from typing import Optional

from app.memory.vector_store import VectorStore, get_vector_store

logger = logging.getLogger(__name__)


class MemoryRetriever:
    """
    High-level memory retrieval interface.

    Wraps VectorStore with additional logic for:
    - Result formatting and deduplication
    - Context window management (token budget)
    - Multi-type filtering

    Attributes:
        vector_store: Underlying VectorStore instance.
        max_context_chars: Maximum characters for retrieved context.
    """

    def __init__(
        self,
        vector_store: Optional[VectorStore] = None,
        max_context_chars: int = 4000,
    ):
        """
        Initialize the Memory Retriever.

        Args:
            vector_store: VectorStore instance (uses shared singleton if None).
            max_context_chars: Max characters for context window.
        """
        self.vector_store = vector_store or get_vector_store()
        self.max_context_chars = max_context_chars

    def retrieve(
        self,
        query: str,
        n_results: int = 5,
        doc_types: Optional[list[str]] = None,
    ) -> str:
        """
        Retrieve and format relevant context for a query.

        Searches across specified document types and formats
        results into a single context string.

        Args:
            query: Search query.
            n_results: Number of results per doc type.
            doc_types: List of doc types to search (None = all).

        Returns:
            Formatted context string ready for prompt injection.
        """
        all_results = []

        if doc_types:
            for dt in doc_types:
                results = self.vector_store.search(
                    query=query, n_results=n_results, doc_type=dt
                )
                all_results.extend(results)
        else:
            all_results = self.vector_store.search(query=query, n_results=n_results)

        # Sort by score (highest first)
        all_results.sort(key=lambda x: x.get("score", 0), reverse=True)

        # Truncate to context window
        context_parts = []
        total_chars = 0
        for r in all_results:
            content = r["content"]
            if total_chars + len(content) > self.max_context_chars:
                # Truncate this result
                remaining = self.max_context_chars - total_chars
                if remaining > 100:
                    content = content[:remaining] + "..."
                    context_parts.append(self._format_result(r, content))
                break
            context_parts.append(self._format_result(r, content))
            total_chars += len(content)

        if not context_parts:
            return ""

        return "\n---\n".join(context_parts)

    @staticmethod
    def _format_result(result: dict, content: str) -> str:
        """Format a single result for context injection."""
        doc_type = result.get("doc_type", "unknown")
        score = result.get("score", 0)
        meta = result.get("metadata", {})
        title = meta.get("title", "Untitled")

        return f"[{doc_type}] {title} (相关度: {score:.2f})\n{content}"
