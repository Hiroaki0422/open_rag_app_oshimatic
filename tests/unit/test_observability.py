import asyncio
import logging

from rag_app.observability.context import correlation_context, current_trace_id
from rag_app.observability.logging import configure_logging, emit_event


def test_structured_event_carries_correlation_and_drops_sensitive_fields(caplog) -> None:  # type: ignore[no-untyped-def]
    logger = logging.getLogger("test.events")
    with (
        caplog.at_level(logging.INFO),
        correlation_context(trace_id="trace-abcdefgh", run_id="run-1"),
    ):
        emit_event(
            logger,
            "provider.completed",
            outcome="success",
            reason_code="provider.ok",
            api_key="never-log-me",
            raw_text="private source",
        )
    record = caplog.records[-1]
    assert record.trace_id == "trace-abcdefgh"
    assert record.run_id == "run-1"
    assert not hasattr(record, "api_key")
    assert "never-log-me" not in caplog.text
    assert record.reason_code == "provider.ok"


def test_concurrent_correlation_contexts_do_not_leak() -> None:
    async def capture(trace_id: str) -> str:
        with correlation_context(trace_id=trace_id):
            await asyncio.sleep(0)
            return current_trace_id()

    async def run() -> list[str]:
        return await asyncio.gather(capture("trace-aaaaaaaa"), capture("trace-bbbbbbbb"))

    assert asyncio.run(run()) == ["trace-aaaaaaaa", "trace-bbbbbbbb"]


def test_configured_truncation_and_sanitized_exception_stack(caplog) -> None:  # type: ignore[no-untyped-def]
    logger = logging.getLogger("test.diagnostics")
    configure_logging("INFO", max_field_length=5)
    try:
        with caplog.at_level(logging.ERROR), correlation_context(trace_id="trace-diagnostic"):
            try:
                raise RuntimeError("secret source payload must not be logged")
            except RuntimeError as exc:
                emit_event(
                    logger,
                    "operation.failed",
                    level=logging.ERROR,
                    stage="application-stage-too-long",
                    outcome="failure",
                    reason_code="internal.failure",
                    provider="provider-name-too-long",
                    exception=exc,
                )
        record = caplog.records[-1]
        assert record.provider == "provi…"
        assert record.stage == "appli…"
        assert record.exception_type == "RuntimeError"
        assert record.trace_id == "trace-diagnostic"
        assert record.severity == "ERROR"
        assert record.timestamp.endswith("+00:00")
        assert record.stack.endswith("…")
        assert len(record.stack) == 6
        assert "secret source payload" not in caplog.text
    finally:
        configure_logging("INFO", max_field_length=512)
