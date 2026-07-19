"""Canonical source, document, hierarchy, and evidence contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, field_validator, model_validator

from .identifiers import DomainModel, HashDigest, PersistedModel, ensure_utc


class RawSourceSnapshot(PersistedModel):
    schema_version: str = "raw-source-snapshot-v1"
    snapshot_id: str = Field(min_length=1)
    artifact_uri: str = Field(min_length=1)
    byte_checksum: HashDigest
    byte_length: int = Field(ge=0)
    media_type: str = Field(min_length=1)
    source_uri: str | None = None
    source_key: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    captured_at: datetime

    @field_validator("captured_at")
    @classmethod
    def normalize_captured_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @model_validator(mode="after")
    def validate_snapshot(self) -> RawSourceSnapshot:
        ensure_utc(self.captured_at)
        if not self.byte_checksum.value.startswith("sha256:raw-bytes-v"):
            raise ValueError("byte_checksum must be an exact raw-bytes digest")
        return self


class DocumentNode(DomainModel):
    node_id: str = Field(min_length=1)
    parent_node_id: str | None = None
    hierarchy_level: int = Field(ge=0)
    title: str | None = None
    text: str
    locator: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_self_parent(self) -> DocumentNode:
        if self.parent_node_id == self.node_id:
            raise ValueError("a document node cannot be its own parent")
        return self


class Document(PersistedModel):
    schema_version: str = "document-v1"
    document_id: str = Field(min_length=1)
    source_snapshot_id: str = Field(min_length=1)
    title: str | None = None
    normalized_text: str
    normalized_content_hash: HashDigest
    nodes: tuple[DocumentNode, ...]
    media_type: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    tenant_id: str | None = None
    access_tags: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_hierarchy(self) -> Document:
        by_id = {node.node_id: node for node in self.nodes}
        if len(by_id) != len(self.nodes):
            raise ValueError("document node identifiers must be unique")
        roots = [node for node in self.nodes if node.parent_node_id is None]
        if self.nodes and len(roots) != 1:
            raise ValueError("a non-empty document hierarchy must have exactly one root")
        for node in self.nodes:
            if node.parent_node_id is None:
                if node.hierarchy_level != 0:
                    raise ValueError("root hierarchy level must be zero")
                continue
            parent = by_id.get(node.parent_node_id)
            if parent is None or node.hierarchy_level != parent.hierarchy_level + 1:
                raise ValueError("node parent must exist at the preceding hierarchy level")
        if not self.normalized_content_hash.value.startswith("sha256:normalized-content-"):
            raise ValueError("normalized_content_hash must declare its normalization version")
        return self


class Chunk(PersistedModel):
    schema_version: str = "chunk-v1"
    chunk_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    parent_node_id: str = Field(min_length=1)
    hierarchy_level: int = Field(ge=0)
    locator: dict[str, Any]
    raw_text: str = Field(min_length=1, json_schema_extra={"sensitive": True})
    contextual_retrieval_text: str | None = Field(
        default=None, json_schema_extra={"generated": True, "not_evidence": True, "sensitive": True}
    )
    token_count: int = Field(gt=0)
    raw_content_hash: HashDigest
    metadata: dict[str, Any] = Field(default_factory=dict)
    tenant_id: str | None = None
    access_tags: tuple[str, ...] = ()
