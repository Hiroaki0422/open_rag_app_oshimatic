from datetime import UTC, datetime
from pathlib import Path

import pytest

from rag_app.config.models import ArtifactSettings, MetadataSettings, Settings
from rag_app.domain.experiments import (
    DatasetSelection,
    ExperimentConfig,
    ExperimentFeatureSnapshot,
    ExperimentIntent,
    SplitRole,
)
from rag_app.domain.identifiers import content_digest, raw_snapshot_digest
from rag_app.domain.indexes import (
    CorpusSnapshotReference,
    EmbeddingBuildIdentity,
    IndexManifestReference,
    LogicalIndexReference,
    ResolvedIndexReference,
)


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


@pytest.fixture
def experiment() -> ExperimentConfig:
    return ExperimentConfig(
        dataset=DatasetSelection(
            name="smoke", version="v1", split="dev", split_role=SplitRole.DEVELOPMENT
        ),
        intent=ExperimentIntent.DEVELOPMENT,
        features=ExperimentFeatureSnapshot(),
        parameters={"retrieval_k": 10, "purpose": "test"},
    )


@pytest.fixture
def resolved_index(now: datetime) -> ResolvedIndexReference:
    return ResolvedIndexReference(
        logical=LogicalIndexReference(logical_name="knowledge", alias="active"),
        physical_index="knowledge-0001",
        index_version="build-v1",
        index_manifest=IndexManifestReference(
            uri="local://indexes/manifest.json",
            checksum=content_digest("artifact", "v1", b"index-manifest"),
        ),
        corpus_snapshot=CorpusSnapshotReference(
            version="corpus-v1", checksum=raw_snapshot_digest(b"corpus")
        ),
        embedding=EmbeddingBuildIdentity(
            provider="example", model="embedding-model", version="2026-01"
        ),
        resolved_at=now,
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        metadata=MetadataSettings(database_path=tmp_path / "metadata" / "runs.sqlite3"),
        artifacts=ArtifactSettings(root_path=tmp_path / "artifacts"),
    )
