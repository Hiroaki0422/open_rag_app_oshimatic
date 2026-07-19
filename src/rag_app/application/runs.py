"""Queued-run application use cases shared by all inbound adapters."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from rag_app.domain.errors import DomainError, IdempotencyConflictError, RunNotFoundError
from rag_app.domain.experiments import ExperimentConfig, ExperimentManifest
from rag_app.domain.identifiers import HashDigest, canonical_digest
from rag_app.domain.indexes import ResolvedIndexReference
from rag_app.domain.runs import RunRecord, RunStatus, RunType
from rag_app.observability.context import correlation_context, current_trace_id
from rag_app.observability.logging import emit_event

from .ports import ArtifactStore, RunRepository

logger = logging.getLogger(__name__)


class CreateRunCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    run_type: RunType
    idempotency_key: str = Field(min_length=1, max_length=256)
    experiment: ExperimentConfig
    resolved_index: ResolvedIndexReference | None = None

    @property
    def request_fingerprint(self) -> HashDigest:
        return canonical_digest(
            "run-request",
            "v1",
            {
                "run_type": self.run_type,
                "experiment": self.experiment,
                "resolved_index": self.resolved_index,
            },
        )


class RunApplicationService:
    def __init__(
        self,
        repository: RunRepository,
        artifacts: ArtifactStore,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.repository = repository
        self.artifacts = artifacts
        self.clock = clock or (lambda: datetime.now(UTC))
        self.id_factory = id_factory or (lambda: uuid4().hex)

    def create(self, command: CreateRunCommand) -> RunRecord:
        with correlation_context():
            try:
                return self._create(command)
            except Exception as exc:
                self._emit_failure("run.create_failed", exc)
                raise

    def _create(self, command: CreateRunCommand) -> RunRecord:
        fingerprint = command.request_fingerprint
        existing = self.repository.get_by_idempotency_key(command.run_type, command.idempotency_key)
        if existing is not None:
            self._ensure_matching_fingerprint(existing, fingerprint)
            return existing

        now = self.clock()
        manifest = ExperimentManifest.create(
            config=command.experiment,
            created_at=now,
            resolved_index=command.resolved_index,
        )
        with correlation_context(experiment_id=manifest.experiment_id):
            reference = self.artifacts.put_manifest(manifest)
            run_id = self.id_factory()
            trace_id = current_trace_id()
            record = RunRecord(
                run_id=run_id,
                run_type=command.run_type,
                status=RunStatus.QUEUED,
                idempotency_key=command.idempotency_key,
                request_fingerprint=fingerprint,
                experiment_id=manifest.experiment_id,
                manifest=reference,
                trace_id=trace_id,
                created_at=now,
                updated_at=now,
            )
            created = self.repository.create(record)
            self._ensure_matching_fingerprint(created, fingerprint)
            with correlation_context(run_id=created.run_id, experiment_id=created.experiment_id):
                emit_event(
                    logger,
                    "run.created",
                    stage="run_creation",
                    outcome="queued",
                    reason_code="run.queued",
                )
            return created

    @staticmethod
    def _ensure_matching_fingerprint(existing: RunRecord, requested: HashDigest) -> None:
        if existing.request_fingerprint != requested:
            raise IdempotencyConflictError(
                "idempotency key was already used with a different request payload"
            )

    def get(self, run_id: str, expected_type: RunType | None = None) -> RunRecord:
        with correlation_context():
            try:
                record = self.repository.get(run_id)
                if record is None or (
                    expected_type is not None and record.run_type != expected_type
                ):
                    raise RunNotFoundError(f"run {run_id!r} was not found")
                return record
            except Exception as exc:
                self._emit_failure("run.get_failed", exc)
                raise

    @staticmethod
    def _emit_failure(event: str, exception: Exception) -> None:
        emit_event(
            logger,
            event,
            level=logging.ERROR,
            stage="application",
            outcome="failure",
            reason_code=(
                exception.reason_code if isinstance(exception, DomainError) else "internal.error"
            ),
            exception=exception,
        )

    def transition(
        self,
        run_id: str,
        status: RunStatus,
        *,
        failure_reason_code: str | None = None,
    ) -> RunRecord:
        with correlation_context():
            try:
                current = self.get(run_id)
                updated = current.transition(
                    status, self.clock(), failure_reason_code=failure_reason_code
                )
                result = self.repository.update_status(run_id, current.status, updated)
                with correlation_context(
                    trace_id=result.trace_id,
                    run_id=result.run_id,
                    experiment_id=result.experiment_id,
                ):
                    emit_event(
                        logger,
                        "run.transitioned",
                        stage="run_lifecycle",
                        outcome=status.value,
                        reason_code=failure_reason_code or f"run.{status.value}",
                    )
                return result
            except Exception as exc:
                self._emit_failure("run.transition_failed", exc)
                raise
