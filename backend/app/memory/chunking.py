"""
Markdown chunking for organizational memory ingestion.

Splits documents by headings/paragraphs while keeping PRD sections
and retrospective case blocks reasonably intact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class TextChunk:
    """A single chunk ready for embedding."""

    content: str
    chunk_index: int
    section_title: str = ""


def chunk_markdown(
    text: str,
    *,
    max_chars: int = 700,
    overlap: int = 80,
) -> list[TextChunk]:
    """
    Chunk markdown text by heading sections, then by size with overlap.

    Args:
        text: Full markdown document.
        max_chars: Soft max characters per chunk.
        overlap: Character overlap between consecutive size-splits.

    Returns:
        List of TextChunk with stable chunk_index ordering.
    """
    text = (text or "").strip()
    if not text:
        return []

    sections = _split_by_headings(text)
    chunks: list[TextChunk] = []

    for section_title, body in sections:
        body = body.strip()
        if not body:
            continue

        if len(body) <= max_chars:
            chunks.append(
                TextChunk(
                    content=_with_title_prefix(section_title, body),
                    chunk_index=len(chunks),
                    section_title=section_title,
                )
            )
            continue

        for piece in _split_with_overlap(body, max_chars=max_chars, overlap=overlap):
            chunks.append(
                TextChunk(
                    content=_with_title_prefix(section_title, piece),
                    chunk_index=len(chunks),
                    section_title=section_title,
                )
            )

    if not chunks:
        chunks.append(TextChunk(content=text[:max_chars], chunk_index=0))

    return chunks


def _with_title_prefix(title: str, body: str) -> str:
    if title and not body.lstrip().startswith("#"):
        return f"## {title}\n\n{body}".strip()
    return body.strip()


def _split_by_headings(text: str) -> list[tuple[str, str]]:
    """Split markdown into (section_title, body) pairs."""
    pattern = re.compile(r"(?m)^(#{1,3})\s+(.+)$")
    matches = list(pattern.finditer(text))
    if not matches:
        return [("", text)]

    sections: list[tuple[str, str]] = []
    # Preamble before first heading
    if matches[0].start() > 0:
        preamble = text[: matches[0].start()].strip()
        if preamble:
            sections.append(("引言", preamble))

    for i, match in enumerate(matches):
        title = match.group(2).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        sections.append((title, body if body else title))

    return sections


def _split_with_overlap(text: str, *, max_chars: int, overlap: int) -> list[str]:
    """Split long text on paragraph boundaries with character overlap."""
    paragraphs = re.split(r"\n\s*\n", text)
    pieces: list[str] = []
    buf = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        candidate = f"{buf}\n\n{para}".strip() if buf else para
        if len(candidate) <= max_chars:
            buf = candidate
            continue
        if buf:
            pieces.append(buf)
            # Overlap tail of previous buffer
            tail = buf[-overlap:] if overlap > 0 and len(buf) > overlap else ""
            buf = f"{tail}\n\n{para}".strip() if tail else para
        else:
            # Single paragraph longer than max — hard split
            for i in range(0, len(para), max_chars - overlap):
                pieces.append(para[i : i + max_chars])
            buf = ""

    if buf:
        pieces.append(buf)
    return pieces
