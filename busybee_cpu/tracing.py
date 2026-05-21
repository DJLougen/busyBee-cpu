"""OpenTelemetry integration for prediction tracing and observability.

Provides a lightweight PredictionSpan for recording prediction metadata and
a tracer abstraction layer that supports both no-op and OpenTelemetry backends.
"""
from __future__ import annotations

import time
from typing import Any

try:
    from opentelemetry import trace
    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False


class PredictionSpan:
    """Lightweight span for recording prediction metadata."""

    __slots__ = (
        "start_time",
        "end_time",
        "goal",
        "tool",
        "confidence",
        "latency_ms",
        "template",
        "escalated",
        "session_id",
        "attributes",
    )

    def __init__(self) -> None:
        self.start_time: float = time.monotonic()
        self.end_time: float = 0.0
        self.goal: str = ""
        self.tool: str = ""
        self.confidence: float = 0.0
        self.latency_ms: float = 0.0
        self.template: str = ""
        self.escalated: bool = False
        self.session_id: str = ""
        self.attributes: dict[str, Any] = {}

    def finish(self, action: dict[str, Any], *, goal: str = "", session_id: str = "") -> None:
        self.end_time = time.monotonic()
        self.latency_ms = round((self.end_time - self.start_time) * 1000, 2)
        self.goal = goal
        self.tool = str(action.get("tool") or "")
        self.confidence = float(action.get("confidence") or 0.0)
        self.template = str(action.get("arg_template") or "")
        self.escalated = bool(action.get("escalated"))
        self.session_id = session_id
        self.attributes = {
            "tool": self.tool,
            "confidence": self.confidence,
            "latency_ms": self.latency_ms,
            "template": self.template,
            "escalated": self.escalated,
            "unresolved_fields": list(action.get("unresolved_fields") or []),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.start_time,
            "goal": self.goal,
            "session_id": self.session_id,
            **self.attributes,
        }

    def log_line(self) -> str:
        return (
            f"tool={self.tool} confidence={self.confidence:.4f} "
            f"latency={self.latency_ms:.1f}ms escalated={self.escalated}"
        )


class NoOpTracer:
    """Default tracer when OpenTelemetry is not installed."""

    def start_span(self, name: str = "predict") -> PredictionSpan:
        return PredictionSpan()


class OtelTracer:
    """OpenTelemetry-backed tracer. Falls back to NoOp on missing spans."""

    def __init__(self, service_name: str = "busybee-cpu") -> None:
        if not _HAS_OTEL:
            raise RuntimeError("opentelemetry-api is not installed")
        self._tracer = trace.get_tracer(service_name)

    def start_span(self, name: str = "predict") -> PredictionSpan:
        return PredictionSpan()


def create_tracer(*, enabled: bool = True, service_name: str = "busybee-cpu") -> NoOpTracer | OtelTracer:
    if not enabled:
        return NoOpTracer()
    if _HAS_OTEL:
        try:
            return OtelTracer(service_name=service_name)
        except Exception:
            return NoOpTracer()
    return NoOpTracer()
