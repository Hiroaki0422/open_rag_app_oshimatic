"""Provider-neutral future query boundary; no query implementation exists in Phase 0."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from .identifiers import PersistedModel
from .indexes import ResolvedIndexReference


class QueryCommand(PersistedModel):
    schema_version: str = "query-command-v1"
    query_id: str = Field(min_length=1)
    query: str = Field(min_length=1, json_schema_extra={"sensitive": True})
    logical_index: str = Field(min_length=1)
    metadata_filters: dict[str, Any] = Field(default_factory=dict)


class Evidence(PersistedModel):
    schema_version: str = "evidence-v1"
    evidence_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    raw_text: str = Field(min_length=1, json_schema_extra={"sensitive": True})
    locator: dict[str, Any]
    score: float | None = None


class Citation(PersistedModel):
    schema_version: str = "citation-v1"
    citation_id: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)
    claim_ids: tuple[str, ...] = Field(min_length=1)


class Claim(PersistedModel):
    schema_version: str = "claim-v1"
    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1, json_schema_extra={"sensitive": True})


class Abstention(PersistedModel):
    schema_version: str = "abstention-v1"
    reason_code: Literal[
        "insufficient_evidence", "unsupported_claims", "provider_failure", "policy"
    ]
    message: str


class QueryResult(PersistedModel):
    schema_version: str = "query-result-v2"
    query_id: str = Field(min_length=1)
    answer: str | None = Field(default=None, json_schema_extra={"sensitive": True})
    abstention: Abstention | None = None
    evidence: tuple[Evidence, ...] = ()
    claims: tuple[Claim, ...] = ()
    citations: tuple[Citation, ...] = ()
    trace_id: str = Field(min_length=1)
    configuration_id: str = Field(min_length=1)
    experiment_id: str = Field(min_length=1)
    resolved_index: ResolvedIndexReference

    @model_validator(mode="after")
    def answer_or_abstain(self) -> QueryResult:
        if (self.answer is None) == (self.abstention is None):
            raise ValueError("query result must contain exactly one of answer or abstention")
        evidence_ids = {item.evidence_id for item in self.evidence}
        if len(evidence_ids) != len(self.evidence):
            raise ValueError("evidence identifiers must be unique")
        citation_ids = {item.citation_id for item in self.citations}
        if len(citation_ids) != len(self.citations):
            raise ValueError("citation identifiers must be unique")
        claim_ids = {item.claim_id for item in self.claims}
        if len(claim_ids) != len(self.claims):
            raise ValueError("claim identifiers must be unique")
        if any(citation.evidence_id not in evidence_ids for citation in self.citations):
            raise ValueError("citations must reference raw evidence")
        cited_claims = {claim_id for citation in self.citations for claim_id in citation.claim_ids}
        if not cited_claims.issubset(claim_ids):
            raise ValueError("citations must reference included claims")
        if self.answer is not None:
            if not self.evidence or not self.citations or not self.claims:
                raise ValueError("answered results require evidence, claims, and citations")
            if cited_claims != claim_ids:
                raise ValueError("every answer claim must have a citation")
        elif self.citations or self.claims:
            raise ValueError("abstentions cannot contain claims or citations")
        return self
