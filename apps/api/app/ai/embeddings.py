"""Legacy embedding helper over LLMManager.embed (kept for existing PI callers)."""

import httpx

from app.ai.errors import GatewayUnavailable
from app.ai.manager import LLMManager
from app.ai.usage import NullUsageStore
from app.core.config import Settings


async def embed(settings: Settings, http: httpx.AsyncClient, texts: list[str]) -> list[list[float]]:
    """One configured embedding space; never mix fallback models' vector spaces.

    Uses OpenAI with the operator-configured ``embedding``/``embed`` model only (callers
    persist that model ID next to stored vectors) and checks settings.embedding_dimensions.
    """
    if not 1 <= len(texts) <= 32:
        raise GatewayUnavailable()
    manager = LLMManager(settings, http, usage=NullUsageStore())
    response = await manager.embed(
        None,
        texts,
        alias="embedding",
        provider="openai",
        expected_dimensions=settings.embedding_dimensions,
        explicit_model_only=True,
    )
    return response.vectors
