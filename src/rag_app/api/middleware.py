"""Correlation and request timing middleware."""

from __future__ import annotations

import logging
import re
from time import perf_counter
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from rag_app.observability.context import correlation_context
from rag_app.observability.logging import emit_event

logger = logging.getLogger(__name__)
TRACE_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,128}$")


class TraceMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        candidate = headers.get(b"x-trace-id", b"").decode("ascii", errors="ignore")
        trace_id = candidate if TRACE_PATTERN.fullmatch(candidate) else uuid4().hex
        started = perf_counter()
        status_code = 500

        async def send_with_trace(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_headers = list(message.get("headers", []))
                response_headers.append((b"x-trace-id", trace_id.encode("ascii")))
                message["headers"] = response_headers
            await send(message)

        with correlation_context(trace_id=trace_id):
            try:
                await self.app(scope, receive, send_with_trace)
            finally:
                emit_event(
                    logger,
                    "http.request",
                    stage="http",
                    duration_ms=round((perf_counter() - started) * 1000, 3),
                    outcome="success" if status_code < 500 else "failure",
                    reason_code="http.completed",
                    status_code=status_code,
                )
