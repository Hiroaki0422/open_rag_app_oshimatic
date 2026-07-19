from datetime import datetime

import pytest

from rag_app.application.runs import CreateRunCommand, RunApplicationService
from rag_app.domain.errors import ArtifactIntegrityError, IdempotencyConflictError, RunNotFoundError
from rag_app.domain.experiments import ExperimentManifest
from rag_app.domain.identifiers import content_digest
from rag_app.domain.runs import ArtifactReference, RunRecord, RunStatus, RunType
from rag_app.observability.context import trace_id_var


class FakeRepository:
    def __init__(self) -> None:
        self.records: dict[str, RunRecord] = {}
        self.created = 0

    def create(self, record: RunRecord) -> RunRecord:
        self.created += 1
        self.records[record.run_id] = record
        return record

    def get(self, run_id: str) -> RunRecord | None:
        return self.records.get(run_id)

    def get_by_idempotency_key(self, run_type: RunType, idempotency_key: str) -> RunRecord | None:
        return next(
            (
                record
                for record in self.records.values()
                if record.run_type == run_type and record.idempotency_key == idempotency_key
            ),
            None,
        )

    def update_status(
        self, run_id: str, expected_status: RunStatus, updated: RunRecord
    ) -> RunRecord:
        assert self.records[run_id].status == expected_status
        self.records[run_id] = updated
        return updated

    def health(self) -> tuple[bool, str | None]:
        return True, None


class FakeArtifacts:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.manifests: list[ExperimentManifest] = []

    def put_manifest(self, manifest: ExperimentManifest) -> ArtifactReference:
        if self.fail:
            raise ArtifactIntegrityError("simulated failure")
        self.manifests.append(manifest)
        payload = manifest.model_dump_json().encode()
        return ArtifactReference(
            uri=f"memory://{manifest.manifest_id.value}",
            checksum=content_digest("artifact", "v1", payload),
            byte_length=len(payload),
        )

    def read(self, reference: ArtifactReference) -> bytes:
        raise NotImplementedError

    def health(self) -> tuple[bool, str | None]:
        return True, None


def service(repo: FakeRepository, artifacts: FakeArtifacts, now: datetime) -> RunApplicationService:
    ids = iter(("run-one", "run-two"))
    return RunApplicationService(repo, artifacts, clock=lambda: now, id_factory=lambda: next(ids))


def test_direct_service_creation_is_queued_and_idempotent(experiment, now) -> None:  # type: ignore[no-untyped-def]
    repo = FakeRepository()
    artifacts = FakeArtifacts()
    application = service(repo, artifacts, now)
    command = CreateRunCommand(
        run_type=RunType.INGESTION, idempotency_key="same-key", experiment=experiment
    )
    first = application.create(command)
    second = application.create(command)
    assert first == second
    assert first.status == RunStatus.QUEUED
    assert repo.created == 1
    assert len(artifacts.manifests) == 1
    assert application.get(first.run_id) == first


def test_manifest_failure_leaves_no_run(experiment, now) -> None:  # type: ignore[no-untyped-def]
    repo = FakeRepository()
    application = service(repo, FakeArtifacts(fail=True), now)
    with pytest.raises(ArtifactIntegrityError):
        application.create(
            CreateRunCommand(
                run_type=RunType.EVALUATION,
                idempotency_key="failure",
                experiment=experiment,
            )
        )
    assert repo.records == {}


def test_get_enforces_run_type_and_not_found(experiment, now) -> None:  # type: ignore[no-untyped-def]
    application = service(FakeRepository(), FakeArtifacts(), now)
    record = application.create(
        CreateRunCommand(run_type=RunType.INGESTION, idempotency_key="key", experiment=experiment)
    )
    with pytest.raises(RunNotFoundError):
        application.get(record.run_id, RunType.EVALUATION)


def test_idempotency_key_rejects_a_different_request(experiment, now) -> None:  # type: ignore[no-untyped-def]
    application = service(FakeRepository(), FakeArtifacts(), now)
    application.create(
        CreateRunCommand(run_type=RunType.INGESTION, idempotency_key="same", experiment=experiment)
    )
    changed = experiment.model_copy(update={"parameters": {"retrieval_k": 11}})
    with pytest.raises(IdempotencyConflictError):
        application.create(
            CreateRunCommand(run_type=RunType.INGESTION, idempotency_key="same", experiment=changed)
        )


class RaceRepository(FakeRepository):
    def __init__(self, winner: RunRecord) -> None:
        super().__init__()
        self.winner = winner

    def get_by_idempotency_key(self, run_type: RunType, idempotency_key: str) -> RunRecord | None:
        return None

    def create(self, record: RunRecord) -> RunRecord:
        return self.winner


def test_race_winner_fingerprint_is_rechecked(experiment, now) -> None:  # type: ignore[no-untyped-def]
    initial = service(FakeRepository(), FakeArtifacts(), now).create(
        CreateRunCommand(run_type=RunType.INGESTION, idempotency_key="race", experiment=experiment)
    )
    changed = experiment.model_copy(update={"parameters": {"retrieval_k": 99}})
    racing = service(RaceRepository(initial), FakeArtifacts(), now)
    with pytest.raises(IdempotencyConflictError):
        racing.create(
            CreateRunCommand(run_type=RunType.INGESTION, idempotency_key="race", experiment=changed)
        )


def test_direct_service_calls_use_isolated_trace_contexts(experiment, now) -> None:  # type: ignore[no-untyped-def]
    application = service(FakeRepository(), FakeArtifacts(), now)
    first = application.create(
        CreateRunCommand(run_type=RunType.INGESTION, idempotency_key="one", experiment=experiment)
    )
    second = application.create(
        CreateRunCommand(run_type=RunType.INGESTION, idempotency_key="two", experiment=experiment)
    )
    assert first.trace_id != second.trace_id
    assert trace_id_var.get() is None
