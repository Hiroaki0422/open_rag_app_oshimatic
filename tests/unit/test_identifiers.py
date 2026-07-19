from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from rag_app.domain.identifiers import (
    HashDigest,
    canonical_digest,
    canonical_json_bytes,
    normalized_content_digest,
    raw_snapshot_digest,
)


def test_canonical_json_is_key_order_independent_and_byte_stable() -> None:
    first = {"b": 2, "a": None, "when": datetime(2026, 1, 1, tzinfo=UTC)}
    second = {
        "when": datetime(2025, 12, 31, 16, tzinfo=timezone(-timedelta(hours=8))),
        "a": None,
        "b": 2,
    }
    expected = b'{"a":null,"b":2,"when":"2026-01-01T00:00:00.000000Z"}'
    assert canonical_json_bytes(first) == expected
    assert canonical_json_bytes(second) == expected
    assert canonical_digest("example", "v1", first) == canonical_digest("example", "v1", second)


def test_raw_and_normalized_hash_namespaces_are_distinct() -> None:
    raw = raw_snapshot_digest(b"hello\r\n")
    normalized = normalized_content_digest("hello\n", "v1")
    assert raw != normalized
    assert raw.value.startswith("sha256:raw-bytes-v1:")
    assert normalized.value.startswith("sha256:normalized-content-v1:")


def test_hash_format_rejects_unversioned_or_malformed_values() -> None:
    with pytest.raises(ValidationError):
        HashDigest(value="sha256:raw:abc")
