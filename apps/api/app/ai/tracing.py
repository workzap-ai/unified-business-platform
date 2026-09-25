"""OpenTelemetry-compatible span hook; a no-op when opentelemetry is not installed."""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Protocol


class SpanLike(Protocol):
    def set_attribute(self, key: str, value: Any) -> None: ...


class _NoopSpan:
    def set_attribute(self, key: str, value: Any) -> None:
        return None


def _load_tracer() -> Any | None:
    try:
        trace = importlib.import_module("opentelemetry.trace")
    except ImportError:
        return None
    return trace.get_tracer("platform.ai")


_tracer = _load_tracer()


@contextmanager
def ai_span(name: str, **attributes: str | int | float | bool | None) -> Iterator[SpanLike]:
    """Span with secret-free attributes (provider, model, alias, attempt...)."""
    if _tracer is None:
        yield _NoopSpan()
        return
    with _tracer.start_as_current_span(name) as span:
        for key, value in attributes.items():
            if value is not None:
                span.set_attribute(f"ai.{key}", value)
        yield span
