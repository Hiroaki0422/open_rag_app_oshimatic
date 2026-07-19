"""SQLite operational metadata adapter."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rag_app.domain.errors import IdempotencyConflictError, InvalidRunTransitionError
from rag_app.domain.identifiers import HashDigest
from rag_app.domain.runs import ArtifactReference, RunRecord, RunStatus, RunType


class SQLiteRunRepository:
    def __init__(self, database_path: Path, busy_timeout_seconds: float = 5.0) -> None:
        self.database_path = database_path
        self.busy_timeout_seconds = busy_timeout_seconds

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(
            self.database_path, timeout=self.busy_timeout_seconds, isolation_level=None
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    def migrate(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        migration_dir = Path(__file__).parent / "migrations"
        migrations: list[tuple[int, Path]] = []
        for path in migration_dir.glob("*.sql"):
            match = re.fullmatch(r"([0-9]{3})_[a-z0-9_]+\.sql", path.name)
            if match is None:
                raise RuntimeError(f"invalid migration filename: {path.name}")
            migrations.append((int(match.group(1)), path))
        migrations.sort()
        versions = [version for version, _path in migrations]
        if versions != list(range(1, len(versions) + 1)):
            raise RuntimeError("migration versions must be unique and contiguous from 001")

        with self._connect() as connection:
            table_exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
            ).fetchone()
            applied = (
                {
                    row[0]
                    for row in connection.execute(
                        "SELECT version FROM schema_migrations"
                    ).fetchall()
                }
                if table_exists
                else set()
            )
            for version, path in migrations:
                if version in applied:
                    continue
                timestamp = datetime.now(UTC).isoformat().replace("'", "''")
                script = path.read_text(encoding="utf-8")
                transactional = (
                    "BEGIN IMMEDIATE;\n"
                    + script
                    + "\nINSERT INTO schema_migrations(version, applied_at) "
                    + f"VALUES ({version}, '{timestamp}');\nCOMMIT;"
                )
                try:
                    connection.executescript(transactional)
                except Exception:
                    if connection.in_transaction:
                        connection.rollback()
                    raise

    def create(self, record: RunRecord) -> RunRecord:
        values = self._to_values(record)
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    f"INSERT INTO runs ({columns}) VALUES ({placeholders})",
                    tuple(values.values()),
                )
                connection.commit()
                return record
            except sqlite3.IntegrityError:
                connection.rollback()
                existing = self._get_by_key(connection, record.run_type, record.idempotency_key)
                if existing is None:
                    raise
                if existing.request_fingerprint != record.request_fingerprint:
                    raise IdempotencyConflictError(
                        "idempotency key was already used with a different request payload"
                    ) from None
                return existing
            except Exception:
                connection.rollback()
                raise

    def get(self, run_id: str) -> RunRecord | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return self._from_row(row) if row else None

    def get_by_idempotency_key(self, run_type: RunType, idempotency_key: str) -> RunRecord | None:
        with self._connect() as connection:
            return self._get_by_key(connection, run_type, idempotency_key)

    def _get_by_key(
        self, connection: sqlite3.Connection, run_type: RunType, idempotency_key: str
    ) -> RunRecord | None:
        row = connection.execute(
            "SELECT * FROM runs WHERE run_type = ? AND idempotency_key = ?",
            (run_type.value, idempotency_key),
        ).fetchone()
        return self._from_row(row) if row else None

    def update_status(
        self, run_id: str, expected_status: RunStatus, updated: RunRecord
    ) -> RunRecord:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """UPDATE runs SET status = ?, updated_at = ?, lease_owner = ?,
                lease_expires_at = ?, failure_reason_code = ?
                WHERE run_id = ? AND status = ?""",
                (
                    updated.status.value,
                    updated.updated_at.isoformat(),
                    updated.lease_owner,
                    updated.lease_expires_at.isoformat() if updated.lease_expires_at else None,
                    updated.failure_reason_code,
                    run_id,
                    expected_status.value,
                ),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                raise InvalidRunTransitionError("run state changed concurrently or does not exist")
            connection.commit()
        return updated

    def health(self) -> tuple[bool, str | None]:
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1").fetchone()
        except (OSError, sqlite3.Error) as exc:
            return False, str(exc)
        return True, None

    @staticmethod
    def _to_values(record: RunRecord) -> dict[str, Any]:
        return {
            "run_id": record.run_id,
            "run_type": record.run_type.value,
            "status": record.status.value,
            "idempotency_key": record.idempotency_key,
            "request_fingerprint": record.request_fingerprint.value,
            "experiment_id": record.experiment_id,
            "manifest_uri": record.manifest.uri,
            "manifest_checksum": record.manifest.checksum.value,
            "manifest_media_type": record.manifest.media_type,
            "manifest_byte_length": record.manifest.byte_length,
            "trace_id": record.trace_id,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
            "lease_owner": record.lease_owner,
            "lease_expires_at": (
                record.lease_expires_at.isoformat() if record.lease_expires_at else None
            ),
            "failure_reason_code": record.failure_reason_code,
            "metadata_json": json.dumps(record.metadata, sort_keys=True, separators=(",", ":")),
            "schema_version": record.schema_version,
        }

    @staticmethod
    def _from_row(row: sqlite3.Row) -> RunRecord:
        return RunRecord(
            schema_version=row["schema_version"],
            run_id=row["run_id"],
            run_type=RunType(row["run_type"]),
            status=RunStatus(row["status"]),
            idempotency_key=row["idempotency_key"],
            request_fingerprint=HashDigest(value=row["request_fingerprint"]),
            experiment_id=row["experiment_id"],
            manifest=ArtifactReference(
                uri=row["manifest_uri"],
                checksum=HashDigest(value=row["manifest_checksum"]),
                media_type=row["manifest_media_type"],
                byte_length=row["manifest_byte_length"],
            ),
            trace_id=row["trace_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            lease_owner=row["lease_owner"],
            lease_expires_at=(
                datetime.fromisoformat(row["lease_expires_at"]) if row["lease_expires_at"] else None
            ),
            failure_reason_code=row["failure_reason_code"],
            metadata=json.loads(row["metadata_json"]),
        )
