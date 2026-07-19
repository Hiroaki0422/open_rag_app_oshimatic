"""Experiment configuration and immutable, content-addressed manifests."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field, model_validator

from .identifiers import HashDigest, PersistedModel, canonical_digest, ensure_utc
from .indexes import ResolvedIndexReference


class ExperimentIntent(StrEnum):
    DEVELOPMENT = "development"
    TUNING = "tuning"
    FINAL_EVALUATION = "final_evaluation"


class SplitRole(StrEnum):
    TRAIN = "train"
    DEVELOPMENT = "development"
    TEST = "test"


class DatasetSelection(PersistedModel):
    schema_version: str = "dataset-selection-v2"
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    split: str = Field(min_length=1)
    split_role: SplitRole


class ExperimentFeatureSnapshot(PersistedModel):
    schema_version: str = "experiment-features-v1"
    semantic_chunking: bool = False
    contextual_headers: bool = False
    dense_retrieval: bool = False
    sparse_retrieval: bool = False
    reranking: bool = False
    metadata_filtering: bool = False
    hierarchical_retrieval: bool = False
    query_rewriting: bool = False
    hyde: bool = False
    multi_hop: bool = False
    dynamic_retrieval: bool = False
    generation: bool = False
    retrieval_sufficiency_gate: bool = False
    citation_support_gate: bool = False


class ComponentVersions(PersistedModel):
    schema_version: str = "component-versions-v1"
    parser: str | None = None
    chunker: str | None = None
    contextualizer: str | None = None
    embedding_model: str | None = None
    embedding: str | None = None
    reranker_model: str | None = None
    reranker: str | None = None
    generator_model: str | None = None
    generator: str | None = None
    prompt: str | None = None
    provider: str | None = None


class ExperimentConfig(PersistedModel):
    schema_version: str = "experiment-config-v3"
    dataset: DatasetSelection
    intent: ExperimentIntent
    features: ExperimentFeatureSnapshot = Field(default_factory=ExperimentFeatureSnapshot)
    versions: ComponentVersions = Field(default_factory=ComponentVersions)
    parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_enabled_versions_and_secrets(self) -> ExperimentConfig:
        if self.dataset.split_role == SplitRole.TEST and (
            self.intent != ExperimentIntent.FINAL_EVALUATION
        ):
            raise ValueError("protected test splits require final_evaluation intent")
        requirements: dict[str, tuple[str, ...]] = {
            "semantic_chunking": ("parser", "chunker"),
            "contextual_headers": ("parser", "chunker", "contextualizer"),
            "dense_retrieval": ("embedding_model", "embedding"),
            "reranking": ("reranker_model", "reranker"),
            "generation": ("generator_model", "generator", "prompt", "provider"),
            "hyde": ("generator_model", "generator", "prompt", "provider"),
            "query_rewriting": ("generator_model", "generator", "prompt", "provider"),
        }
        missing = [
            field
            for feature, fields in requirements.items()
            if getattr(self.features, feature)
            for field in fields
            if getattr(self.versions, field) is None
        ]
        if missing:
            raise ValueError(
                "enabled experiment features require version fields: "
                + ", ".join(sorted(set(missing)))
            )
        secret_names = {"api_key", "authorization", "password", "secret", "token"}

        def contains_secret(value: Any) -> bool:
            if isinstance(value, dict):
                return any(
                    any(secret in str(key).lower() for secret in secret_names)
                    or contains_secret(item)
                    for key, item in value.items()
                )
            if isinstance(value, (list, tuple)):
                return any(contains_secret(item) for item in value)
            return False

        if contains_secret(self.parameters):
            raise ValueError("experiment parameters must not contain secrets")
        return self

    def identity_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="python")

    @property
    def experiment_id(self) -> str:
        return str(canonical_digest("experiment", "v3", self.identity_payload()))


class ExperimentManifest(PersistedModel):
    schema_version: str = "experiment-manifest-v3"
    manifest_id: HashDigest
    experiment_id: str = Field(min_length=1)
    config: ExperimentConfig
    resolved_index: ResolvedIndexReference | None = None

    @classmethod
    def create(
        cls,
        config: ExperimentConfig,
        created_at: datetime,
        resolved_index: ResolvedIndexReference | None = None,
    ) -> ExperimentManifest:
        ensure_utc(created_at)
        identity = {
            "schema_version": "experiment-manifest-v3",
            "experiment_id": config.experiment_id,
            "config": config,
            "resolved_index": resolved_index,
        }
        return cls(
            manifest_id=canonical_digest("manifest", "v3", identity),
            experiment_id=config.experiment_id,
            config=config,
            resolved_index=resolved_index,
        )

    @model_validator(mode="after")
    def validate_identity(self) -> ExperimentManifest:
        identity = {
            "schema_version": self.schema_version,
            "experiment_id": self.experiment_id,
            "config": self.config,
            "resolved_index": self.resolved_index,
        }
        expected = canonical_digest("manifest", "v3", identity)
        if expected != self.manifest_id or self.experiment_id != self.config.experiment_id:
            raise ValueError("manifest identity does not match its identity-bearing payload")
        return self
