from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from rag_app.domain.benchmarks import (
    BenchmarkQuery,
    CorpusDocument,
    DatasetDescriptor,
    ExpectedAnswer,
    RelevanceJudgment,
)
from rag_app.domain.documents import Chunk, Document, DocumentNode, RawSourceSnapshot
from rag_app.domain.identifiers import (
    content_digest,
    normalized_content_digest,
    raw_snapshot_digest,
)
from rag_app.domain.indexes import ResolvedIndexReference
from rag_app.domain.queries import Abstention, Citation, Claim, Evidence, QueryResult


def test_raw_snapshot_normalizes_aware_timestamp_to_utc() -> None:
    snapshot = RawSourceSnapshot(
        snapshot_id="snapshot-1",
        artifact_uri="local://raw/1",
        byte_checksum=raw_snapshot_digest(b"raw"),
        byte_length=3,
        media_type="text/plain",
        source_key="one",
        source_version="v1",
        captured_at=datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=9))),
    )
    assert snapshot.captured_at.utcoffset() == timedelta(0)
    assert RawSourceSnapshot.model_validate_json(snapshot.model_dump_json()) == snapshot


def test_raw_snapshot_rejects_naive_timestamp_and_normalized_hash() -> None:
    values = {
        "snapshot_id": "snapshot-1",
        "artifact_uri": "local://raw/1",
        "byte_checksum": raw_snapshot_digest(b"raw"),
        "byte_length": 3,
        "media_type": "text/plain",
        "source_key": "one",
        "source_version": "v1",
        "captured_at": datetime(2026, 1, 1),
    }
    with pytest.raises(ValidationError, match="timezone-aware"):
        RawSourceSnapshot(**values)
    values["captured_at"] = datetime.now(UTC)
    values["byte_checksum"] = normalized_content_digest("raw", "v1")
    with pytest.raises(ValidationError, match="raw-bytes"):
        RawSourceSnapshot(**values)


def test_document_hierarchy_is_validated() -> None:
    root = DocumentNode(node_id="root", hierarchy_level=0, text="root")
    child = DocumentNode(node_id="child", parent_node_id="root", hierarchy_level=1, text="child")
    document = Document(
        document_id="doc",
        source_snapshot_id="snapshot",
        normalized_text="root child",
        normalized_content_hash=normalized_content_digest("root child", "v1"),
        nodes=(root, child),
        media_type="text/plain",
    )
    assert document.nodes[1].parent_node_id == "root"
    with pytest.raises(ValidationError, match="preceding hierarchy"):
        Document(
            **{
                **document.model_dump(),
                "nodes": (root, child.model_copy(update={"hierarchy_level": 2})),
            }
        )


def test_generated_retrieval_context_remains_distinct_from_raw_evidence() -> None:
    chunk = Chunk(
        chunk_id="chunk-1",
        document_id="doc-1",
        parent_node_id="node-1",
        hierarchy_level=1,
        locator={"page": 1},
        raw_text="authoritative source",
        contextual_retrieval_text="generated header",
        token_count=2,
        raw_content_hash=content_digest("normalized-content", "v1", b"authoritative source"),
    )
    evidence = Evidence(
        evidence_id="e1",
        document_id=chunk.document_id,
        chunk_id=chunk.chunk_id,
        raw_text=chunk.raw_text,
        locator=chunk.locator,
    )
    assert evidence.raw_text != chunk.contextual_retrieval_text
    with pytest.raises(ValidationError):
        Evidence.model_validate({**evidence.model_dump(), "hyde_passage": "generated"})


def test_benchmark_assets_have_non_interchangeable_discriminators() -> None:
    dataset = DatasetDescriptor(name="sample", version="v1", split="dev")
    assets = (
        CorpusDocument(
            dataset=dataset,
            external_document_id="d1",
            source_key="d1",
            media_type="text/plain",
            content="source",
        ),
        BenchmarkQuery(dataset=dataset, query_id="q1", query="question"),
        RelevanceJudgment(dataset=dataset, query_id="q1", document_id="d1", relevance=1),
        ExpectedAnswer(dataset=dataset, query_id="q1", answers=("answer",)),
    )
    assert {asset.asset_type for asset in assets} == {
        "corpus_document",
        "query",
        "relevance_judgment",
        "expected_answer",
    }
    with pytest.raises(ValidationError):
        CorpusDocument.model_validate(assets[1].model_dump())


def test_resolved_index_requires_complete_immutable_identity(resolved_index) -> None:  # type: ignore[no-untyped-def]
    assert resolved_index.physical_index == "knowledge-0001"
    assert (
        ResolvedIndexReference.model_validate_json(resolved_index.model_dump_json())
        == resolved_index
    )
    with pytest.raises(ValidationError, match="physical index"):
        ResolvedIndexReference.model_validate(
            {**resolved_index.model_dump(), "physical_index": resolved_index.logical.alias}
        )
    incomplete = resolved_index.model_dump()
    del incomplete["index_manifest"]
    with pytest.raises(ValidationError):
        ResolvedIndexReference.model_validate(incomplete)


def test_query_result_requires_exact_index_and_evidence_backed_citations(
    resolved_index,
) -> None:  # type: ignore[no-untyped-def]
    evidence = Evidence(
        evidence_id="e1",
        document_id="d1",
        chunk_id="c1",
        raw_text="source",
        locator={"page": 1},
    )
    result = QueryResult(
        query_id="q1",
        answer="answer",
        evidence=(evidence,),
        claims=(Claim(claim_id="claim-1", text="answer"),),
        citations=(Citation(citation_id="cite-1", evidence_id="e1", claim_ids=("claim-1",)),),
        trace_id="trace-1",
        configuration_id="config-1",
        experiment_id="experiment-1",
        resolved_index=resolved_index,
    )
    assert result.resolved_index.physical_index == "knowledge-0001"
    with pytest.raises(ValidationError, match="exactly one"):
        QueryResult(
            **{**result.model_dump(), "abstention": Abstention(reason_code="policy", message="no")}
        )
    with pytest.raises(ValidationError, match="raw evidence"):
        QueryResult(
            **{
                **result.model_dump(),
                "citations": (
                    Citation(
                        citation_id="cite-2",
                        evidence_id="missing",
                        claim_ids=("claim-1",),
                    ),
                ),
            }
        )
    with pytest.raises(ValidationError, match="require evidence"):
        QueryResult(
            query_id="q2",
            answer="uncited",
            trace_id="trace-2",
            configuration_id="config-1",
            experiment_id="experiment-1",
            resolved_index=resolved_index,
        )
    with pytest.raises(ValidationError, match="identifiers must be unique"):
        QueryResult(**{**result.model_dump(), "citations": result.citations + result.citations})
    abstention = QueryResult(
        query_id="q3",
        abstention=Abstention(reason_code="insufficient_evidence", message="not enough"),
        evidence=(evidence,),
        trace_id="trace-3",
        configuration_id="config-1",
        experiment_id="experiment-1",
        resolved_index=resolved_index,
    )
    assert abstention.evidence == (evidence,)


@pytest.mark.parametrize(
    "contract",
    [RawSourceSnapshot, Document, CorpusDocument, BenchmarkQuery, ResolvedIndexReference],
)
def test_boundary_contracts_generate_json_schema(contract: type[object]) -> None:
    schema = contract.model_json_schema()  # type: ignore[attr-defined]
    assert schema["type"] == "object"
