import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Barrier

import pytest

from rag_app.application.runs import CreateRunCommand, RunApplicationService
from rag_app.domain.errors import ArtifactIntegrityError, IdempotencyConflictError
from rag_app.domain.experiments import ExperimentManifest
from rag_app.domain.runs import RunStatus, RunType
from rag_app.infrastructure.artifacts.local import LocalArtifactStore
from rag_app.infrastructure.sqlite.runs import SQLiteRunRepository

pytestmark = pytest.mark.integration


def test_local_artifact_is_immutable_verified_and_reloadable(tmp_path, experiment, now) -> None:  # type: ignore[no-untyped-def]
    store = LocalArtifactStore(tmp_path / "artifacts")
    manifest = ExperimentManifest.create(experiment, now)
    first = store.put_manifest(manifest)
    second = store.put_manifest(manifest)
    assert first == second
    payload = store.read(first)
    assert json.loads(payload)["manifest_id"]["value"] == manifest.manifest_id.value

    path = store.root / first.uri.removeprefix("local://")
    path.write_bytes(b"tampered")
    with pytest.raises(ArtifactIntegrityError):
        store.read(first)


def test_sqlite_migration_idempotency_lifecycle_and_storage_split(
    tmp_path, experiment, now
) -> None:  # type: ignore[no-untyped-def]
    database = tmp_path / "metadata" / "runs.sqlite3"
    repository = SQLiteRunRepository(database)
    repository.migrate()
    repository.migrate()
    service = RunApplicationService(
        repository,
        LocalArtifactStore(tmp_path / "artifacts"),
        clock=lambda: now,
        id_factory=iter(("run-one", "run-two")).__next__,
    )
    command = CreateRunCommand(
        run_type=RunType.EVALUATION, idempotency_key="request-1", experiment=experiment
    )
    first = service.create(command)
    assert service.create(command).run_id == first.run_id
    running = service.transition(first.run_id, RunStatus.RUNNING)
    assert running.status == RunStatus.RUNNING

    with closing(sqlite3.connect(database)) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        columns = {row[1] for row in connection.execute("PRAGMA table_info(runs)")}
        count = connection.execute("SELECT count(*) FROM runs").fetchone()[0]
    assert count == 1
    assert tables == {"runs", "schema_migrations"}
    assert not {"manifest_json", "document", "span", "trace"} & columns


def test_sqlite_failed_insert_rolls_back(tmp_path, experiment, now) -> None:  # type: ignore[no-untyped-def]
    repository = SQLiteRunRepository(tmp_path / "runs.sqlite3")
    repository.migrate()
    service = RunApplicationService(
        repository,
        LocalArtifactStore(tmp_path / "artifacts"),
        clock=lambda: now,
        id_factory=lambda: "same-run-id",
    )
    first = service.create(
        CreateRunCommand(run_type=RunType.INGESTION, idempotency_key="first", experiment=experiment)
    )
    assert first.run_id == "same-run-id"
    with pytest.raises(sqlite3.IntegrityError):
        service.create(
            CreateRunCommand(
                run_type=RunType.INGESTION, idempotency_key="second", experiment=experiment
            )
        )
    with closing(sqlite3.connect(repository.database_path)) as connection:
        assert connection.execute("SELECT count(*) FROM runs").fetchone()[0] == 1


def test_migration_upgrades_an_existing_version_one_database(tmp_path) -> None:  # type: ignore[no-untyped-def]
    database = tmp_path / "legacy.sqlite3"
    migration = Path("src/rag_app/infrastructure/sqlite/migrations/001_runs.sql").read_text(
        encoding="utf-8"
    )
    with closing(sqlite3.connect(database)) as connection:
        connection.executescript(migration)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (1, '2026-01-01T00:00:00Z')"
        )
        connection.execute(
            """INSERT INTO runs (
                run_id, run_type, status, idempotency_key, experiment_id,
                manifest_uri, manifest_checksum, manifest_media_type, manifest_byte_length,
                trace_id, created_at, updated_at, lease_owner, lease_expires_at,
                failure_reason_code, metadata_json, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "legacy-run",
                "ingestion",
                "queued",
                "legacy-key",
                "legacy-experiment",
                "local://manifests/legacy.json",
                "sha256:artifact-v1:1111111111111111111111111111111111111111111111111111111111111111",
                "application/json",
                2,
                "legacy-trace",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
                None,
                None,
                None,
                "{}",
                "run-record-v1",
            ),
        )
        connection.commit()
    repository = SQLiteRunRepository(database)
    repository.migrate()
    with closing(sqlite3.connect(database)) as connection:
        versions = [
            row[0]
            for row in connection.execute("SELECT version FROM schema_migrations ORDER BY version")
        ]
        columns = {row[1] for row in connection.execute("PRAGMA table_info(runs)")}
    assert versions == [1, 2]
    assert "request_fingerprint" in columns
    legacy = repository.get("legacy-run")
    assert legacy is not None
    assert legacy.request_fingerprint.value.endswith("0" * 64)


class BarrierRepository(SQLiteRunRepository):
    def __init__(self, database_path, barrier: Barrier) -> None:  # type: ignore[no-untyped-def]
        super().__init__(database_path)
        self.barrier = barrier

    def get_by_idempotency_key(self, run_type: RunType, idempotency_key: str):  # type: ignore[no-untyped-def]
        result = super().get_by_idempotency_key(run_type, idempotency_key)
        self.barrier.wait(timeout=5)
        return result


def test_sqlite_race_is_payload_aware(tmp_path, experiment, now) -> None:  # type: ignore[no-untyped-def]
    database = tmp_path / "race.sqlite3"
    SQLiteRunRepository(database).migrate()
    artifacts = LocalArtifactStore(tmp_path / "artifacts")

    def submit(config) -> str:  # type: ignore[no-untyped-def]
        repository = BarrierRepository(database, barrier)
        service = RunApplicationService(repository, artifacts, clock=lambda: now)
        return service.create(
            CreateRunCommand(
                run_type=RunType.INGESTION,
                idempotency_key="race-key",
                experiment=config,
            )
        ).run_id

    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        matching = list(pool.map(submit, (experiment, experiment)))
    assert matching[0] == matching[1]

    other_database = tmp_path / "conflict.sqlite3"
    SQLiteRunRepository(other_database).migrate()
    barrier = Barrier(2)
    database = other_database
    changed = experiment.model_copy(update={"parameters": {"retrieval_k": 999}})
    outcomes: list[str] = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(submit, config) for config in (experiment, changed)]
        for future in futures:
            try:
                outcomes.append(future.result())
            except IdempotencyConflictError:
                outcomes.append("conflict")
    assert outcomes.count("conflict") == 1
