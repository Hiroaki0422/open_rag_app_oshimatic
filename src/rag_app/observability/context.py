"""Request-safe correlation context."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from uuid import uuid4

trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)
run_id_var: ContextVar[str | None] = ContextVar("run_id", default=None)
query_id_var: ContextVar[str | None] = ContextVar("query_id", default=None)
experiment_id_var: ContextVar[str | None] = ContextVar("experiment_id", default=None)


def current_trace_id() -> str:
    return trace_id_var.get() or uuid4().hex


def correlations() -> dict[str, str]:
    values = {
        "trace_id": current_trace_id(),
        "run_id": run_id_var.get(),
        "query_id": query_id_var.get(),
        "experiment_id": experiment_id_var.get(),
    }
    return {name: value for name, value in values.items() if value is not None}


@contextmanager
def correlation_context(
    *,
    trace_id: str | None = None,
    run_id: str | None = None,
    query_id: str | None = None,
    experiment_id: str | None = None,
) -> Iterator[str]:
    tokens: list[tuple[ContextVar[str | None], Token[str | None]]] = []
    values = (
        (trace_id_var, trace_id or trace_id_var.get() or uuid4().hex),
        (run_id_var, run_id),
        (query_id_var, query_id),
        (experiment_id_var, experiment_id),
    )
    try:
        for variable, value in values:
            if value is not None:
                tokens.append((variable, variable.set(value)))
        yield current_trace_id()
    finally:
        for variable, token in reversed(tokens):
            variable.reset(token)
