"""Text embeddings for the example bank (pi Brain spec 8.4.3), when the platform has them.

The platform's one configured embedding model (settings `openai_models["embedding"]`, with
`semantic_search_enabled`) is used for both the stored examples and the person's message, so the
two always live in the same vector space. Without it, or when a call fails, nothing breaks: the
bank falls back to matching on shared words. An embedding only ever changes which examples are
chosen, never whether a text passes the redaction gate or the never-learn list.
"""

import logging
from collections.abc import Awaitable, Callable

import httpx

from app.core.config import Settings

logger = logging.getLogger("app.pi.learning")

Embedder = Callable[[list[str]], Awaitable[list[list[float]] | None]]


def make_embedder(settings: Settings, http: httpx.AsyncClient | None) -> Embedder | None:
    """An embedder for this deployment, or None when embeddings are not configured."""
    if http is None or not settings.semantic_search_enabled:
        return None
    if not settings.openai_models.get("embedding"):
        return None

    async def run(texts: list[str]) -> list[list[float]] | None:
        from app.ai.embeddings import embed

        try:
            vectors = await embed(settings, http, texts[:32])
        except Exception:  # noqa: BLE001 - embeddings are an extra, never a reason to fail a turn
            logger.warning("pi_learning_embedding_failed")
            return None
        return vectors if len(vectors) == len(texts[:32]) else None

    return run
