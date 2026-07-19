import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from rag_app.config.models import FeatureFlags, OpenSearchSettings, RetrievalSettings, Settings
from rag_app.domain.experiments import (
    ComponentVersions,
    DatasetSelection,
    ExperimentConfig,
    ExperimentFeatureSnapshot,
    ExperimentIntent,
    SplitRole,
)


def test_phase_zero_defaults_disable_all_future_features() -> None:
    settings = Settings(_env_file=None)
    assert settings.features.enabled() == ()


def test_nested_environment_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_API__PORT", "8123")
    monkeypatch.setenv("RAG_RETRIEVAL__RETRIEVAL_K", "30")
    settings = Settings(_env_file=None)
    assert settings.api.port == 8123
    assert settings.retrieval.retrieval_k == 30


def test_unimplemented_capability_fails_at_startup() -> None:
    with pytest.raises(ValidationError, match="must remain disabled"):
        Settings(features=FeatureFlags(hyde=True), _env_file=None)


def test_invalid_timeout_and_budget_fail() -> None:
    with pytest.raises(ValidationError):
        OpenSearchSettings(health_timeout_seconds=-1)
    with pytest.raises(ValidationError, match="rerank_k"):
        RetrievalSettings(retrieval_k=5, rerank_k=6)


def test_config_display_redacts_secrets() -> None:
    settings = Settings(opensearch=OpenSearchSettings(password="highly-secret"), _env_file=None)
    rendered = json.dumps(settings.redacted_dict())
    assert "highly-secret" not in rendered
    assert "**********" in rendered


def test_experiment_rejects_secrets_and_requires_enabled_capability_versions() -> None:
    dataset = DatasetSelection(
        name="sample", version="v1", split="dev", split_role=SplitRole.DEVELOPMENT
    )
    with pytest.raises(ValidationError, match="must not contain secrets"):
        ExperimentConfig(
            dataset=dataset,
            intent=ExperimentIntent.DEVELOPMENT,
            parameters={"nested": [{"api_key": "do-not-store"}]},
        )
    with pytest.raises(ValidationError, match="embedding"):
        ExperimentConfig(
            dataset=dataset,
            intent=ExperimentIntent.DEVELOPMENT,
            features=ExperimentFeatureSnapshot(dense_retrieval=True),
        )
    complete = ExperimentConfig(
        dataset=dataset,
        intent=ExperimentIntent.DEVELOPMENT,
        features=ExperimentFeatureSnapshot(dense_retrieval=True),
        versions=ComponentVersions(embedding_model="embed", embedding="v1"),
    )
    assert complete.versions.embedding == "v1"


def test_experiment_rejects_unknown_flags_and_protected_split_tuning() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        ExperimentFeatureSnapshot.model_validate({"dense_retreival": True})
    with pytest.raises(ValidationError, match="split_role"):
        DatasetSelection(name="sample", version="v1", split="challenge")
    with pytest.raises(ValidationError, match="final_evaluation"):
        ExperimentConfig(
            dataset=DatasetSelection(
                name="sample", version="v1", split="test", split_role=SplitRole.TEST
            ),
            intent=ExperimentIntent.TUNING,
        )
    final = ExperimentConfig(
        dataset=DatasetSelection(
            name="sample", version="v1", split="test", split_role=SplitRole.TEST
        ),
        intent=ExperimentIntent.FINAL_EVALUATION,
    )
    assert final.intent == ExperimentIntent.FINAL_EVALUATION


@pytest.mark.parametrize("split", ["test-v1", "blind_test", "challenge"])
@pytest.mark.parametrize("intent", [ExperimentIntent.TUNING, ExperimentIntent.DEVELOPMENT])
def test_dataset_specific_test_names_cannot_bypass_split_role(split, intent) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValidationError, match="final_evaluation"):
        ExperimentConfig(
            dataset=DatasetSelection(
                name="sample", version="v1", split=split, split_role=SplitRole.TEST
            ),
            intent=intent,
        )


def test_split_name_does_not_override_explicit_non_test_role() -> None:
    config = ExperimentConfig(
        dataset=DatasetSelection(
            name="sample",
            version="v1",
            split="test-v1",
            split_role=SplitRole.DEVELOPMENT,
        ),
        intent=ExperimentIntent.TUNING,
    )
    assert config.dataset.split_role == SplitRole.DEVELOPMENT


def test_checked_in_example_uses_the_current_experiment_schema() -> None:
    payload = json.loads(Path("experiments/configs/phase0-example.json").read_text())
    config = ExperimentConfig.model_validate(payload)
    assert config.schema_version == "experiment-config-v3"
    assert config.dataset.split_role == SplitRole.DEVELOPMENT
