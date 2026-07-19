from datetime import timedelta

import pytest
from pydantic import ValidationError

from rag_app.domain.errors import InvalidRunTransitionError
from rag_app.domain.identifiers import canonical_digest, content_digest
from rag_app.domain.runs import ArtifactReference, RunRecord, RunStatus, RunType


def make_run(now) -> RunRecord:  # type: ignore[no-untyped-def]
    payload = b"{}"
    return RunRecord(
        run_id="run-1",
        run_type=RunType.INGESTION,
        status=RunStatus.QUEUED,
        idempotency_key="request-1",
        request_fingerprint=canonical_digest("run-request", "v1", {"request": 1}),
        experiment_id="experiment-1",
        manifest=ArtifactReference(
            uri="local://manifests/one.json",
            checksum=content_digest("artifact", "v1", payload),
            byte_length=len(payload),
        ),
        trace_id="trace-12345678",
        created_at=now,
        updated_at=now,
    )


def test_valid_run_lifecycle(now) -> None:  # type: ignore[no-untyped-def]
    queued = make_run(now)
    running = queued.transition(RunStatus.RUNNING, now + timedelta(seconds=1))
    succeeded = running.transition(RunStatus.SUCCEEDED, now + timedelta(seconds=2))
    assert succeeded.status == RunStatus.SUCCEEDED


def test_invalid_transition_and_failed_reason(now) -> None:  # type: ignore[no-untyped-def]
    queued = make_run(now)
    with pytest.raises(InvalidRunTransitionError):
        queued.transition(RunStatus.SUCCEEDED, now)
    running = queued.transition(RunStatus.RUNNING, now)
    with pytest.raises(InvalidRunTransitionError, match="reason"):
        running.transition(RunStatus.FAILED, now)
    assert (
        running.transition(RunStatus.FAILED, now, failure_reason_code="worker.crashed").status
        == RunStatus.FAILED
    )


def test_transition_revalidates_timestamps_and_failure_state(now) -> None:  # type: ignore[no-untyped-def]
    queued = make_run(now)
    with pytest.raises(InvalidRunTransitionError, match="backward"):
        queued.transition(RunStatus.RUNNING, now - timedelta(microseconds=1))
    with pytest.raises(InvalidRunTransitionError, match="only valid"):
        queued.transition(
            RunStatus.RUNNING, now + timedelta(seconds=1), failure_reason_code="not.failed"
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"updated_at": "backward"}, "updated_at"),
        ({"failure_reason_code": "not.failed"}, "only valid"),
        ({"status": RunStatus.FAILED}, "require"),
        ({"lease_owner": "worker"}, "set together"),
        ({"lease_expires_at": "future"}, "set together"),
        (
            {
                "status": RunStatus.RUNNING,
                "lease_owner": "worker",
                "lease_expires_at": "past",
            },
            "follow updated_at",
        ),
    ],
)
def test_direct_construction_rejects_invalid_invariants(now, changes, message) -> None:  # type: ignore[no-untyped-def]
    values = make_run(now).model_dump()
    replacements = {
        "backward": now - timedelta(seconds=1),
        "future": now + timedelta(seconds=10),
        "past": now - timedelta(seconds=1),
    }
    values.update({key: replacements.get(value, value) for key, value in changes.items()})
    with pytest.raises(ValidationError, match=message):
        RunRecord.model_validate(values)


def test_all_lifecycle_edges_are_enforced(now) -> None:  # type: ignore[no-untyped-def]
    allowed = {
        (RunStatus.QUEUED, RunStatus.RUNNING),
        (RunStatus.QUEUED, RunStatus.CANCELLED),
        (RunStatus.RUNNING, RunStatus.SUCCEEDED),
        (RunStatus.RUNNING, RunStatus.FAILED),
        (RunStatus.RUNNING, RunStatus.CANCELLED),
    }
    base = make_run(now)
    for source in RunStatus:
        source_values = base.model_dump()
        source_values["status"] = source
        source_values["failure_reason_code"] = (
            "already.failed" if source == RunStatus.FAILED else None
        )
        record = RunRecord.model_validate(source_values)
        for target in RunStatus:
            reason = "transition.failed" if target == RunStatus.FAILED else None
            if (source, target) in allowed:
                assert record.transition(target, now, failure_reason_code=reason).status == target
            else:
                with pytest.raises(InvalidRunTransitionError):
                    record.transition(target, now, failure_reason_code=reason)
