"""Logical and exactly resolved index identity contracts."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator, model_validator

from .identifiers import HashDigest, PersistedModel, ensure_utc


class LogicalIndexReference(PersistedModel):
    schema_version: str = "logical-index-reference-v1"
    logical_name: str = Field(min_length=1)
    alias: str = Field(min_length=1)


class IndexManifestReference(PersistedModel):
    schema_version: str = "index-manifest-reference-v1"
    uri: str = Field(min_length=1)
    checksum: HashDigest


class CorpusSnapshotReference(PersistedModel):
    schema_version: str = "corpus-snapshot-reference-v1"
    version: str = Field(min_length=1)
    checksum: HashDigest


class EmbeddingBuildIdentity(PersistedModel):
    schema_version: str = "embedding-build-identity-v1"
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    version: str = Field(min_length=1)


class ResolvedIndexReference(PersistedModel):
    schema_version: str = "resolved-index-reference-v2"
    logical: LogicalIndexReference
    physical_index: str = Field(min_length=1)
    index_version: str = Field(min_length=1)
    index_manifest: IndexManifestReference
    corpus_snapshot: CorpusSnapshotReference
    embedding: EmbeddingBuildIdentity
    resolved_at: datetime

    @field_validator("resolved_at")
    @classmethod
    def normalize_resolved_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @model_validator(mode="after")
    def validate_resolution(self) -> ResolvedIndexReference:
        ensure_utc(self.resolved_at)
        if self.physical_index == self.logical.alias:
            raise ValueError("physical index must not be the logical alias")
        return self
