"""Composition root and FastAPI dependency accessors."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from rag_app.application.readiness import PortHealthAdapter, ReadinessApplicationService
from rag_app.application.runs import RunApplicationService
from rag_app.config.models import Settings
from rag_app.infrastructure.artifacts.local import LocalArtifactStore
from rag_app.infrastructure.opensearch.health import OpenSearchHealth
from rag_app.infrastructure.sqlite.runs import SQLiteRunRepository


@dataclass(frozen=True)
class Services:
    runs: RunApplicationService
    readiness: ReadinessApplicationService


def compose_services(settings: Settings) -> Services:
    repository = SQLiteRunRepository(
        settings.metadata.database_path, settings.metadata.busy_timeout_seconds
    )
    repository.migrate()
    artifacts = LocalArtifactStore(settings.artifacts.root_path)
    runs = RunApplicationService(repository, artifacts)
    readiness = ReadinessApplicationService(
        (
            PortHealthAdapter("sqlite", repository),
            PortHealthAdapter("artifacts", artifacts),
            OpenSearchHealth(settings.opensearch.url, settings.opensearch.health_timeout_seconds),
        )
    )
    return Services(runs=runs, readiness=readiness)


def get_services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services
