"""Typed, startup-validated application settings."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SettingsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AppSettings(SettingsModel):
    name: str = "rag-app"
    environment: Literal["development", "test", "production"] = "development"
    schema_version: str = "api-v1"


class ApiSettings(SettingsModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)


class MetadataSettings(SettingsModel):
    database_path: Path = Path("var/metadata/rag.sqlite3")
    busy_timeout_seconds: float = Field(default=5.0, gt=0)


class ArtifactSettings(SettingsModel):
    root_path: Path = Path("var/artifacts")


class OpenSearchSettings(SettingsModel):
    url: str = Field(default="http://localhost:9200", pattern=r"^https?://")
    health_timeout_seconds: float = Field(default=2.0, gt=0)
    username: str | None = None
    password: SecretStr | None = None


class ProviderSettings(SettingsModel):
    model_provider: str | None = None
    model_name: str | None = None
    api_key: SecretStr | None = None
    timeout_seconds: float = Field(default=30.0, gt=0)


class VersionSettings(SettingsModel):
    parser: str | None = None
    chunker: str | None = None
    contextualizer: str | None = None
    embedding: str | None = None
    prompt: str | None = None
    dataset: str | None = None


class RetrievalSettings(SettingsModel):
    retrieval_k: int = Field(default=20, gt=0)
    rerank_k: int = Field(default=10, gt=0)
    context_token_budget: int = Field(default=4096, gt=0)
    max_multi_hop_steps: int = Field(default=3, gt=0)
    sufficiency_threshold: float = Field(default=0.5, ge=0, le=1)
    citation_support_threshold: float = Field(default=0.8, ge=0, le=1)

    @model_validator(mode="after")
    def validate_budgets(self) -> RetrievalSettings:
        if self.rerank_k > self.retrieval_k:
            raise ValueError("rerank_k cannot exceed retrieval_k")
        return self


class DynamicProviderSettings(SettingsModel):
    timeout_seconds: float = Field(default=5.0, gt=0)
    cache_ttl_seconds: int = Field(default=300, ge=0)
    failure_behavior: Literal["fallback", "fail"] = "fallback"


class EvaluationSettings(SettingsModel):
    max_concurrency: int = Field(default=1, gt=0)


class ObservabilitySettings(SettingsModel):
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    max_field_length: int = Field(default=512, gt=0, le=16384)


class FeatureFlags(SettingsModel):
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

    def enabled(self) -> tuple[str, ...]:
        return tuple(name for name, value in self.model_dump().items() if value)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RAG_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app: AppSettings = Field(default_factory=AppSettings)
    api: ApiSettings = Field(default_factory=ApiSettings)
    metadata: MetadataSettings = Field(default_factory=MetadataSettings)
    artifacts: ArtifactSettings = Field(default_factory=ArtifactSettings)
    opensearch: OpenSearchSettings = Field(default_factory=OpenSearchSettings)
    providers: ProviderSettings = Field(default_factory=ProviderSettings)
    versions: VersionSettings = Field(default_factory=VersionSettings)
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    dynamic_providers: DynamicProviderSettings = Field(default_factory=DynamicProviderSettings)
    evaluation: EvaluationSettings = Field(default_factory=EvaluationSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    features: FeatureFlags = Field(default_factory=FeatureFlags)

    @field_validator("metadata")
    @classmethod
    def validate_database_path(cls, value: MetadataSettings) -> MetadataSettings:
        if value.database_path.exists() and value.database_path.is_dir():
            raise ValueError("metadata.database_path must be a file, not a directory")
        return value

    @field_validator("artifacts")
    @classmethod
    def validate_artifact_path(cls, value: ArtifactSettings) -> ArtifactSettings:
        if value.root_path.exists() and not value.root_path.is_dir():
            raise ValueError("artifacts.root_path must be a directory")
        return value

    @model_validator(mode="after")
    def reject_unimplemented_features(self) -> Settings:
        if enabled := self.features.enabled():
            names = ", ".join(enabled)
            raise ValueError(
                "Phase 0 capability is not implemented and must remain disabled: " + names
            )
        return self

    def redacted_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")
