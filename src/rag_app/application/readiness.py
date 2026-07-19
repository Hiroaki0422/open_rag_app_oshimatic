"""Framework-neutral readiness use case."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from rag_app.observability.logging import emit_event

from .ports import DependencyHealth

logger = logging.getLogger(__name__)


class HealthPort(Protocol):
    def health(self) -> tuple[bool, str | None]: ...


class DependencyState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    ready: bool
    detail: str | None = None


class ReadinessResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    ready: bool
    dependencies: dict[str, DependencyState]


class ReadinessApplicationService:
    def __init__(self, dependencies: Iterable[DependencyHealth]) -> None:
        self.dependencies = tuple(dependencies)

    def check(self) -> ReadinessResult:
        states: dict[str, DependencyState] = {}
        for dependency in self.dependencies:
            try:
                healthy, detail = dependency.check()
            except Exception as exc:
                healthy = False
                detail = f"{type(exc).__name__}: dependency check failed"
                emit_event(
                    logger,
                    "readiness.dependency_failed",
                    level=logging.ERROR,
                    stage="readiness",
                    outcome="failure",
                    reason_code="dependency.check_failed",
                    dependency=dependency.name,
                    exception=exc,
                )
            states[dependency.name] = DependencyState(ready=healthy, detail=detail)
        return ReadinessResult(
            ready=all(state.ready for state in states.values()), dependencies=states
        )


class PortHealthAdapter:
    def __init__(self, name: str, port: HealthPort) -> None:
        self.name = name
        self.port = port

    def check(self) -> tuple[bool, str | None]:
        return self.port.health()
