"""Canonical serialization and content-addressed identity helpers."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

HASH_PATTERN = r"^sha256:[a-z][a-z0-9_.-]*-v[1-9][0-9]*:[0-9a-f]{64}$"


class DomainModel(BaseModel):
    """Strict, immutable base for persisted and API-boundary contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)


class HashDigest(DomainModel):
    value: str = Field(pattern=HASH_PATTERN)

    def __str__(self) -> str:
        return self.value


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


class PersistedModel(DomainModel):
    schema_version: str = Field(pattern=r"^[a-z][a-z0-9_.-]*-v[1-9][0-9]*$")


class UtcTimestampModel(DomainModel):
    @field_validator("*", mode="before")
    @classmethod
    def validate_datetime_fields(cls, value: Any) -> Any:
        return ensure_utc(value) if isinstance(value, datetime) else value


def _canonicalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _canonicalize(value.model_dump(mode="python"))
    if isinstance(value, datetime):
        return ensure_utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _canonicalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    return value


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize as canonical UTF-8 JSON with explicit nulls and stable separators."""

    return json.dumps(
        _canonicalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def content_digest(kind: str, schema_version: str, payload: bytes) -> HashDigest:
    prefix = f"{kind}-{schema_version}"
    if not prefix.removesuffix("-v1").replace("-", "").replace("_", "").isalnum():
        raise ValueError("hash kind and schema version must form a stable identifier")
    digest = hashlib.sha256(prefix.encode() + b"\0" + payload).hexdigest()
    return HashDigest(value=f"sha256:{prefix}:{digest}")


def canonical_digest(kind: str, schema_version: str, value: Any) -> HashDigest:
    return content_digest(kind, schema_version, canonical_json_bytes(value))


def raw_snapshot_digest(original_bytes: bytes) -> HashDigest:
    """Hash exact source bytes; this is intentionally not a normalized-content hash."""

    return content_digest("raw-bytes", "v1", original_bytes)


def normalized_content_digest(normalized_text: str, normalization_version: str) -> HashDigest:
    return content_digest("normalized-content", normalization_version, normalized_text.encode())


def document_id(source_namespace: str, stable_external_key: str) -> str:
    return str(
        canonical_digest(
            "document-id", "v1", {"namespace": source_namespace, "key": stable_external_key}
        )
    )


def chunk_id(
    document_identifier: str, chunker_version: str, hierarchy_level: int, locator: dict[str, Any]
) -> str:
    return str(
        canonical_digest(
            "chunk-id",
            "v1",
            {
                "document_id": document_identifier,
                "chunker_version": chunker_version,
                "hierarchy_level": hierarchy_level,
                "locator": locator,
            },
        )
    )
