"""Separated benchmark asset contracts."""

from typing import Any, Literal

from pydantic import Field

from .identifiers import DomainModel, PersistedModel


class DatasetDescriptor(PersistedModel):
    schema_version: str = "dataset-descriptor-v1"
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    split: str = Field(min_length=1)


class CorpusDocument(PersistedModel):
    schema_version: str = "benchmark-corpus-document-v1"
    asset_type: Literal["corpus_document"] = "corpus_document"
    dataset: DatasetDescriptor
    external_document_id: str = Field(min_length=1)
    source_key: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    content: str = Field(json_schema_extra={"sensitive": True})
    metadata: dict[str, Any] = Field(default_factory=dict)


class BenchmarkQuery(PersistedModel):
    schema_version: str = "benchmark-query-v1"
    asset_type: Literal["query"] = "query"
    dataset: DatasetDescriptor
    query_id: str = Field(min_length=1)
    query: str = Field(min_length=1, json_schema_extra={"sensitive": True})
    metadata: dict[str, Any] = Field(default_factory=dict)


class RelevanceJudgment(PersistedModel):
    schema_version: str = "relevance-judgment-v1"
    asset_type: Literal["relevance_judgment"] = "relevance_judgment"
    dataset: DatasetDescriptor
    query_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    relevance: int = Field(ge=0)
    evidence_locators: tuple[dict[str, Any], ...] = ()


class ExpectedAnswer(PersistedModel):
    schema_version: str = "expected-answer-v1"
    asset_type: Literal["expected_answer"] = "expected_answer"
    dataset: DatasetDescriptor
    query_id: str = Field(min_length=1)
    answers: tuple[str, ...] = ()
    label: str | None = None
    answerable: bool | None = None


class BenchmarkExample(DomainModel):
    """Evaluation-only view; deliberately not accepted by ingestion contracts."""

    query: BenchmarkQuery
    judgments: tuple[RelevanceJudgment, ...] = ()
    expected_answer: ExpectedAnswer | None = None
