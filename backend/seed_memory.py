"""
Seed organizational memory with sample Markdown docs and rebuild Org Profile.

Usage (from backend/):
  python seed_memory.py
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("seed_memory")

SAMPLE_DIR = Path(__file__).resolve().parent / "sample_memory"

DOC_TYPE_BY_NAME = {
    "01_ai_resume_prd.md": "prd",
    "02_todo_app_prd.md": "prd",
    "03_meeting_notes.md": "meeting_note",
    "04_retro_smart_report.md": "stress_test",
    "05_onboarding_prd.md": "prd",
}


async def main() -> None:
    from app.memory.vector_store import VectorStore, set_vector_store
    from app.memory.org_profile import rebuild_org_profile

    if not SAMPLE_DIR.exists():
        raise SystemExit(f"Sample dir not found: {SAMPLE_DIR}")

    store = VectorStore()
    set_vector_store(store)

    files = sorted(SAMPLE_DIR.glob("*.md"))
    if not files:
        raise SystemExit("No sample markdown files found")

    for path in files:
        content = path.read_text(encoding="utf-8")
        doc_type = DOC_TYPE_BY_NAME.get(path.name, "other")
        title = path.stem
        doc_id = store.add_document(
            content=content,
            metadata={"title": title, "source": path.name},
            doc_type=doc_type,
        )
        logger.info("Seeded %s -> %s (%s)", path.name, doc_id, doc_type)

    samples = store.get_sample_texts()
    profile = await rebuild_org_profile(samples)
    stats = store.get_stats()
    logger.info("Stats: %s", stats)
    logger.info(
        "Org Profile lessons=%s terms=%s",
        len(profile.get("lessons_learned") or []),
        len((profile.get("terminology") or {}).get("mapping") or {}),
    )
    logger.info("Done. Persist dir: %s", stats.get("persist_dir"))


if __name__ == "__main__":
    asyncio.run(main())
