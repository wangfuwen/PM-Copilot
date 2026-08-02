"""
ChromaDB Vector Store — 向量存储管理。

Persistent ChromaDB + OpenAI embeddings for organizational memory.
"""

from __future__ import annotations

import uuid
import logging
from pathlib import Path
from typing import Optional

import chromadb

from app.config import settings
from app.memory.chunking import chunk_markdown

logger = logging.getLogger(__name__)

_store_singleton: Optional["VectorStore"] = None


def get_vector_store() -> "VectorStore":
    """Return the process-wide VectorStore singleton."""
    global _store_singleton
    if _store_singleton is None:
        _store_singleton = VectorStore()
    return _store_singleton


def set_vector_store(store: "VectorStore") -> None:
    """Inject a VectorStore instance (used by FastAPI lifespan)."""
    global _store_singleton
    _store_singleton = store


class VectorStore:
    """
    ChromaDB-based vector store for organizational memory.

    Stores chunked documents with OpenAI embeddings for:
    - Historical PRDs
    - Decision records
    - Stress test results
    - Meeting notes and product insights
    """

    def __init__(self):
        persist_dir = Path(settings.chroma_persist_dir)
        if not persist_dir.is_absolute():
            # Resolve relative to backend working directory
            persist_dir = Path.cwd() / persist_dir
        persist_dir.mkdir(parents=True, exist_ok=True)

        self.persist_dir = persist_dir
        self.client = chromadb.PersistentClient(path=str(persist_dir))
        self.collection = self.client.get_or_create_collection(
            name=settings.chroma_collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._embeddings = None
        logger.info(
            "VectorStore initialized: collection='%s', path=%s, count=%s",
            settings.chroma_collection_name,
            persist_dir,
            self.collection.count(),
        )

    @property
    def embeddings(self):
        """Lazy-load embedding model."""
        if self._embeddings is None:
            self._embeddings = settings.get_embedding_model()
        return self._embeddings

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self.embeddings.embed_documents(texts)
        return vectors

    def _embed_query(self, query: str) -> list[float]:
        return self.embeddings.embed_query(query)

    def add_document(
        self,
        content: str,
        metadata: dict | None = None,
        doc_type: str = "other",
        doc_id: str | None = None,
        *,
        chunk: bool = True,
    ) -> str:
        """
        Add a document (optionally chunked) to the vector store.

        Returns:
            Parent document ID.
        """
        parent_id = doc_id or str(uuid.uuid4())
        meta = dict(metadata or {})
        title = meta.get("title") or meta.get("source") or "Untitled"
        source = meta.get("source") or title

        if chunk:
            pieces = chunk_markdown(content)
        else:
            from app.memory.chunking import TextChunk

            pieces = [TextChunk(content=content, chunk_index=0, section_title=title)]

        if not pieces:
            raise ValueError("Document content is empty after chunking")

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict] = []

        for piece in pieces:
            chunk_id = f"{parent_id}::chunk-{piece.chunk_index}"
            ids.append(chunk_id)
            documents.append(piece.content)
            metadatas.append(
                {
                    "doc_type": doc_type,
                    "parent_id": parent_id,
                    "chunk_index": piece.chunk_index,
                    "title": title,
                    "source": source,
                    "section_title": piece.section_title or "",
                    "content_length": len(piece.content),
                    "is_chunk": True,
                }
            )

        embeddings = self._embed_texts(documents)
        self.collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )
        logger.info(
            "Added document parent_id=%s type=%s chunks=%s",
            parent_id,
            doc_type,
            len(pieces),
        )
        return parent_id

    def search(
        self,
        query: str,
        n_results: int = 5,
        doc_type: Optional[str] = None,
        doc_types: Optional[list[str]] = None,
    ) -> list[dict]:
        """Search for relevant chunks by semantic similarity."""
        count = self.collection.count()
        if count == 0:
            return []

        where_filter = None
        if doc_type:
            where_filter = {"doc_type": doc_type}
        elif doc_types:
            if len(doc_types) == 1:
                where_filter = {"doc_type": doc_types[0]}
            else:
                where_filter = {"doc_type": {"$in": doc_types}}

        query_embedding = self._embed_query(query)
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(n_results, count),
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )

        formatted: list[dict] = []
        if not results or not results.get("documents"):
            return formatted

        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i] if results.get("metadatas") else {}
            distance = results["distances"][0][i] if results.get("distances") else 0.0
            score = 1.0 - (distance / 2.0)
            formatted.append(
                {
                    "doc_id": meta.get("parent_id", ""),
                    "chunk_id": results["ids"][0][i] if results.get("ids") else "",
                    "content": doc,
                    "metadata": meta,
                    "score": round(score, 4),
                    "doc_type": meta.get("doc_type", "unknown"),
                    "title": meta.get("title", "Untitled"),
                }
            )
        return formatted

    def list_documents(self) -> list[dict]:
        """List unique parent documents (deduped from chunks)."""
        count = self.collection.count()
        if count == 0:
            return []

        raw = self.collection.get(include=["metadatas", "documents"])
        parents: dict[str, dict] = {}
        ids = raw.get("ids") or []
        metas = raw.get("metadatas") or []
        docs_raw = raw.get("documents") or []

        for i, meta in enumerate(metas):
            parent_id = meta.get("parent_id") or (
                ids[i].split("::")[0] if i < len(ids) else ""
            )
            if not parent_id:
                continue
            preview = (docs_raw[i] or "")[:200]
            chunk_index = int(meta.get("chunk_index") or 0)
            if parent_id not in parents:
                parents[parent_id] = {
                    "doc_id": parent_id,
                    "title": meta.get("title", "Untitled"),
                    "doc_type": meta.get("doc_type", "other"),
                    "source": meta.get("source", ""),
                    "chunk_count": 1,
                    "_min_chunk": chunk_index,
                    "preview": preview,
                }
                continue
            parents[parent_id]["chunk_count"] += 1
            if chunk_index < parents[parent_id]["_min_chunk"]:
                parents[parent_id]["_min_chunk"] = chunk_index
                parents[parent_id]["preview"] = preview

        docs = list(parents.values())
        for d in docs:
            d.pop("_min_chunk", None)
        docs.sort(key=lambda d: d.get("title", ""))
        return docs

    def delete_document(self, doc_id: str) -> bool:
        """Delete a parent document and all its chunks."""
        try:
            # Delete by parent_id metadata, and also exact id for legacy single-doc rows
            try:
                self.collection.delete(where={"parent_id": doc_id})
            except Exception:
                pass
            try:
                self.collection.delete(ids=[doc_id])
            except Exception:
                pass
            # Also delete chunk ids with prefix
            raw = self.collection.get(include=[])
            chunk_ids = [i for i in (raw.get("ids") or []) if i.startswith(f"{doc_id}::")]
            if chunk_ids:
                self.collection.delete(ids=chunk_ids)
            logger.info("Deleted document: id=%s", doc_id)
            return True
        except Exception as e:
            logger.error("Failed to delete document %s: %s", doc_id, e)
            return False

    def get_sample_texts(self, max_docs: int = 8, max_chars_each: int = 1500) -> list[dict]:
        """Sample parent documents for Org Profile extraction."""
        docs = self.list_documents()
        samples: list[dict] = []
        for doc in docs[:max_docs]:
            parent_id = doc["doc_id"]
            raw = self.collection.get(
                where={"parent_id": parent_id},
                include=["documents", "metadatas"],
            )
            parts = []
            for content, meta in zip(raw.get("documents") or [], raw.get("metadatas") or []):
                parts.append((meta.get("chunk_index", 0), content))
            parts.sort(key=lambda x: x[0])
            full = "\n\n".join(p[1] for p in parts)
            samples.append(
                {
                    "doc_id": parent_id,
                    "title": doc.get("title", "Untitled"),
                    "doc_type": doc.get("doc_type", "other"),
                    "content": full[:max_chars_each],
                }
            )
        return samples

    def get_chunk(self, chunk_id: str) -> dict | None:
        """Fetch a single chunk by id for citation preview."""
        if not chunk_id:
            return None
        try:
            raw = self.collection.get(ids=[chunk_id], include=["documents", "metadatas"])
        except Exception as e:
            logger.warning("get_chunk failed for %s: %s", chunk_id, e)
            return None
        if not raw or not raw.get("ids"):
            return None
        meta = (raw.get("metadatas") or [{}])[0] or {}
        content = (raw.get("documents") or [""])[0] or ""
        return {
            "chunk_id": chunk_id,
            "doc_id": meta.get("parent_id", ""),
            "title": meta.get("title", "Untitled"),
            "doc_type": meta.get("doc_type", "unknown"),
            "section_title": meta.get("section_title", ""),
            "content": content,
            "metadata": meta,
        }

    def get_stats(self) -> dict:
        """Get statistics about the vector store."""
        docs = self.list_documents()
        return {
            "collection_name": settings.chroma_collection_name,
            "chunk_count": self.collection.count(),
            "document_count": len(docs),
            "persist_dir": str(self.persist_dir),
        }
