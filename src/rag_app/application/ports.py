"""Narrow outbound ports owned by the application layer."""

from typing import Protocol

from rag_app.domain.experiments import ExperimentManifest
from rag_app.domain.runs import ArtifactReference, RunRecord, RunStatus, RunType


class RunRepository(Protocol):
    def create(self, record: RunRecord) -> RunRecord: ...

    def get(self, run_id: str) -> RunRecord | None: ...

    def get_by_idempotency_key(
        self, run_type: RunType, idempotency_key: str
    ) -> RunRecord | None: ...

    def update_status(
        self,
        run_id: str,
        expected_status: RunStatus,
        updated: RunRecord,
    ) -> RunRecord: ...

    def health(self) -> tuple[bool, str | None]: ...


class ArtifactStore(Protocol):
    def put_manifest(self, manifest: ExperimentManifest) -> ArtifactReference: ...

    def read(self, reference: ArtifactReference) -> bytes: ...

    def health(self) -> tuple[bool, str | None]: ...


class DependencyHealth(Protocol):
    name: str

    def check(self) -> tuple[bool, str | None]: ...
