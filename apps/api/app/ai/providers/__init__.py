"""Provider adapters (httpx only). Import concrete adapters from their modules."""

from app.ai.providers.base import (
    EmbeddingProvider,
    LLMProvider,
    SpeechToTextProvider,
    VisionProvider,
)

__all__ = ["EmbeddingProvider", "LLMProvider", "SpeechToTextProvider", "VisionProvider"]
