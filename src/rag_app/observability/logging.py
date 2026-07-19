"""Structured events, redaction, and exporter-compatible telemetry interfaces."""

from __future__ import annotations

import logging
import sys
import traceback
from datetime import UTC, datetime
from typing import Any, Protocol

from pythonjsonlogger.json import JsonFormatter

from .context import correlations

SENSITIVE_NAMES = frozenset(
    {
        "api_key",
        "authorization",
        "context",
        "document",
        "password",
        "payload",
        "prompt",
        "query",
        "raw_bytes",
        "raw_text",
        "secret",
        "source",
        "token",
    }
)
ALLOWED_EVENT_FIELDS = frozenset(
    {
        "event",
        "timestamp",
        "severity",
        "stage",
        "duration_ms",
        "outcome",
        "reason_code",
        "trace_id",
        "run_id",
        "query_id",
        "experiment_id",
        "index_version",
        "token_count",
        "cost_units",
        "cache_status",
        "retry_count",
        "provider",
        "dependency",
        "status_code",
        "exception_type",
        "stack",
    }
)
IDENTITY_EVENT_FIELDS = frozenset(
    {
        "event",
        "timestamp",
        "severity",
        "outcome",
        "reason_code",
        "trace_id",
        "run_id",
        "query_id",
        "experiment_id",
        "exception_type",
    }
)

_configured_max_field_length = 512


class _RagLogHandler(logging.StreamHandler[Any]):
    pass


class Span(Protocol):
    def set_attribute(self, name: str, value: str | int | float | bool) -> None: ...

    def record_exception(self, exception: BaseException) -> None: ...


class Tracer(Protocol):
    def start_as_current_span(self, name: str) -> Any: ...


class Metrics(Protocol):
    def record(self, name: str, value: float, attributes: dict[str, str]) -> None: ...


def configure_logging(level: str = "INFO", max_field_length: int = 512) -> None:
    global _configured_max_field_length
    _configured_max_field_length = max_field_length
    handler = _RagLogHandler(sys.stdout)
    handler.setFormatter(JsonFormatter("%(timestamp)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    for existing in tuple(root.handlers):
        if isinstance(existing, _RagLogHandler):
            root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)


def _safe_fields(fields: dict[str, Any], max_length: int) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for name, value in fields.items():
        lowered = name.lower()
        if name not in ALLOWED_EVENT_FIELDS or any(key in lowered for key in SENSITIVE_NAMES):
            continue
        if isinstance(value, str) and len(value) > max_length and name not in IDENTITY_EVENT_FIELDS:
            safe[name] = value[:max_length] + "…"
        elif isinstance(value, (str, int, float, bool)) or value is None:
            safe[name] = value
    return safe


def emit_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    max_length: int | None = None,
    exception: BaseException | None = None,
    **fields: Any,
) -> None:
    data = {
        "timestamp": datetime.now(UTC).isoformat(),
        "severity": logging.getLevelName(level),
        "event": event,
        **correlations(),
        **fields,
    }
    limit = max_length if max_length is not None else _configured_max_field_length
    if exception is not None:
        data["exception_type"] = type(exception).__name__
        frames = traceback.extract_tb(exception.__traceback__)
        data["stack"] = " <- ".join(
            f"{frame.filename}:{frame.lineno}:{frame.name}" for frame in reversed(frames)
        )
    logger.log(level, event, extra=_safe_fields(data, limit))
