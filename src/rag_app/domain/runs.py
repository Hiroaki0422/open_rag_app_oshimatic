"""Asynchronous execution metadata and lifecycle."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator, model_validator

from .errors import InvalidRunTransitionError
from .identifiers import HashDigest, PersistedModel, ensure_utc


class RunType(StrEnum):
    INGESTION = "ingestion"
    EVALUATION = "evaluation"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


ALLOWED_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.QUEUED: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED}),
    RunStatus.RUNNING: frozenset({RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}),
    RunStatus.SUCCEEDED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.CANCELLED: frozenset(),
}


class ArtifactReference(PersistedModel):
    schema_version: str = "artifact-reference-v1"
    uri: str = Field(min_length=1)
    checksum: HashDigest
    media_type: str = "application/json"
    byte_length: int = Field(ge=0)


class RunRecord(PersistedModel):
    schema_version: str = "run-record-v2"
    run_id: str = Field(min_length=1)
    run_type: RunType
    status: RunStatus
    idempotency_key: str = Field(min_length=1)
    request_fingerprint: HashDigest
    experiment_id: str = Field(min_length=1)
    manifest: ArtifactReference
    trace_id: str = Field(min_length=1)
    created_at: datetime
    updated_at: datetime
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    failure_reason_code: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("created_at", "updated_at", "lease_expires_at")
    @classmethod
    def normalize_timestamps(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value) if value is not None else None

    @model_validator(mode="after")
    def validate_invariants(self) -> RunRecord:
        ensure_utc(self.created_at)
        ensure_utc(self.updated_at)
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        if (self.lease_owner is None) != (self.lease_expires_at is None):
            raise ValueError("lease owner and expiration must be set together")
        if self.lease_owner is not None and self.status != RunStatus.RUNNING:
            raise ValueError("only running runs may hold a lease")
        if self.lease_expires_at is not None and self.lease_expires_at <= self.updated_at:
            raise ValueError("lease expiration must follow updated_at")
        if self.status == RunStatus.FAILED:
            if not self.failure_reason_code:
                raise ValueError("failed runs require a stable failure reason code")
        elif self.failure_reason_code is not None:
            raise ValueError("failure_reason_code is only valid for failed runs")
        return self

    def transition(
        self,
        status: RunStatus,
        at: datetime,
        *,
        failure_reason_code: str | None = None,
    ) -> RunRecord:
        if status not in ALLOWED_TRANSITIONS[self.status]:
            raise InvalidRunTransitionError(f"cannot transition {self.status} to {status}")
        normalized_at = ensure_utc(at)
        if normalized_at < self.updated_at:
            raise InvalidRunTransitionError("transition timestamp cannot move backward")
        if status == RunStatus.FAILED and not failure_reason_code:
            raise InvalidRunTransitionError("failed runs require a stable failure reason code")
        if status != RunStatus.FAILED and failure_reason_code is not None:
            raise InvalidRunTransitionError("failure reason is only valid for failed runs")
        values = self.model_dump(mode="python")
        values.update(
            {
                "status": status,
                "updated_at": normalized_at,
                "failure_reason_code": failure_reason_code,
                "lease_owner": None,
                "lease_expires_at": None,
            }
        )
        try:
            return RunRecord.model_validate(values)
        except ValueError as exc:
            raise InvalidRunTransitionError(str(exc)) from exc
