"""Legacy text-generation facade over LLMManager (kept for existing PI callers).

Provider text is untrusted and never authorizes actions. New code should use
``app.ai.manager.LLMManager`` with a WorkspaceScope (budgets + usage metering).
The facade does not persist usage: its callers write ``Gateway.attempts`` rows.
"""

import httpx
from pydantic import BaseModel, Field

from app.ai.errors import (
    AllProvidersFailed,
    GatewayUnavailable,
    PermanentProviderFailure,
    UsageLimitExceeded,
)
from app.ai.manager import LLMManager
from app.ai.types import Attempt, Message
from app.ai.usage import NullUsageStore
from app.core.config import Settings

__all__ = [
    "AllProvidersFailed",
    "Attempt",
    "Gateway",
    "GatewayUnavailable",
    "Generation",
    "PermanentProviderFailure",
    "UsageLimitExceeded",
]

MAX_TEXT = 32000


class Generation(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT)
    provider: str
    model: str
    attempts: list[Attempt]


class Gateway:
    def __init__(
        self, settings: Settings, http: httpx.AsyncClient, manager: LLMManager | None = None
    ) -> None:
        self.settings, self.http = settings, http
        self.manager = manager or LLMManager(settings, http, usage=NullUsageStore())
        self.attempts: list[Attempt] = []

    async def generate(self, system: str, user: str, alias: str = "fast") -> Generation:
        self.attempts = []
        if len(user) > MAX_TEXT or len(system) > MAX_TEXT:
            raise GatewayUnavailable()
        try:
            response = await self.manager.complete(
                None,
                alias=alias,
                purpose="generate",
                messages=[Message.system(system), Message.user(user)],
                max_tokens=1500,
            )
        except GatewayUnavailable as exc:
            self.attempts = exc.attempts
            raise
        self.attempts = response.attempts
        if not response.text.strip() or len(response.text) > MAX_TEXT:
            raise GatewayUnavailable(response.attempts)
        return Generation(
            text=response.text,
            provider=response.provider,
            model=response.model,
            attempts=response.attempts,
        )
