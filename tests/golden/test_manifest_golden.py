from datetime import UTC, datetime, timedelta
from pathlib import Path

from rag_app.domain.experiments import ExperimentConfig, ExperimentManifest
from rag_app.domain.identifiers import canonical_json_bytes


def config(**changes: object) -> ExperimentConfig:
    values = {
        "dataset": {
            "name": "golden",
            "version": "v1",
            "split": "dev",
            "split_role": "development",
        },
        "intent": "development",
        "features": {"generation": False, "dense_retrieval": False},
        "versions": {},
        "parameters": {"retrieval_k": 10},
    }
    values.update(changes)
    return ExperimentConfig.model_validate(values)


def test_manifest_format_and_hash_are_golden() -> None:
    manifest = ExperimentManifest.create(config(), datetime(2026, 1, 1, tzinfo=UTC))
    expected = Path("tests/fixtures/experiment_manifest_v3.json").read_bytes().rstrip(b"\n")
    assert canonical_json_bytes(manifest) == expected
    assert (
        manifest.manifest_id.value
        == "sha256:manifest-v3:d9c776783bb2bf41d57c0fc38f0660eec371920f2080205cfae911cf2a7dc3c2"
    )


def test_creation_time_is_volatile_but_identity_bearing_version_is_not() -> None:
    first = ExperimentManifest.create(config(), datetime(2026, 1, 1, tzinfo=UTC))
    later = ExperimentManifest.create(
        config(), datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=1)
    )
    changed = ExperimentManifest.create(
        config(versions={"chunker": "chunker-v2"}), datetime(2026, 1, 1, tzinfo=UTC)
    )
    assert canonical_json_bytes(first) == canonical_json_bytes(later)
    assert first.manifest_id == later.manifest_id
    assert changed.manifest_id != first.manifest_id
