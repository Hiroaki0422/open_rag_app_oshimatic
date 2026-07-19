import logging

from fastapi.testclient import TestClient

from rag_app.api.app import create_app
from rag_app.api.dependencies import Services
from rag_app.application.readiness import ReadinessApplicationService
from rag_app.application.runs import RunApplicationService
from rag_app.config.models import Settings

from .test_application_services import FakeArtifacts, FakeRepository, service
from .test_readiness import Check, ThrowingCheck


def client(now) -> tuple[TestClient, RunApplicationService]:  # type: ignore[no-untyped-def]
    runs = service(FakeRepository(), FakeArtifacts(), now)
    readiness = ReadinessApplicationService((Check("sqlite", True), Check("search", False)))
    services = Services(runs=runs, readiness=readiness)
    app = create_app(Settings(_env_file=None), services)
    return TestClient(app), runs


def request_body(experiment) -> dict[str, object]:  # type: ignore[no-untyped-def]
    return {"experiment": experiment.model_dump(mode="json")}


def test_post_returns_queued_run_location_and_propagated_trace(experiment, now) -> None:  # type: ignore[no-untyped-def]
    api, _runs = client(now)
    response = api.post(
        "/v1/ingestion-runs",
        json=request_body(experiment),
        headers={"Idempotency-Key": "request-1", "X-Trace-ID": "trace-abcdefgh"},
    )
    assert response.status_code == 202
    assert response.headers["x-trace-id"] == "trace-abcdefgh"
    assert response.json()["run"]["status"] == "queued"
    location = response.headers["location"]
    inspected = api.get(location)
    assert inspected.json() == response.json()


def test_run_type_is_enforced_at_inspection(experiment, now) -> None:  # type: ignore[no-untyped-def]
    api, _runs = client(now)
    created = api.post(
        "/v1/ingestion-runs",
        json=request_body(experiment),
        headers={"Idempotency-Key": "request-1"},
    ).json()["run"]
    response = api.get(f"/v1/evaluation-runs/{created['run_id']}")
    assert response.status_code == 404
    assert response.json()["reason_code"] == "run.not_found"


def test_liveness_survives_failed_readiness_and_schema_has_no_placeholders(now) -> None:  # type: ignore[no-untyped-def]
    api, _runs = client(now)
    assert api.get("/healthz").status_code == 200
    readiness = api.get("/readyz")
    assert readiness.status_code == 503
    assert readiness.json()["dependencies"]["search"]["ready"] is False
    paths = api.get("/openapi.json").json()["paths"]
    assert "/v1/query" not in paths
    assert not any(path.startswith("/v1/traces") for path in paths)


def test_validation_errors_are_machine_readable(now) -> None:  # type: ignore[no-untyped-def]
    api, _runs = client(now)
    response = api.post("/v1/evaluation-runs", json={})
    assert response.status_code == 422
    assert response.json()["schema_version"] == "error-v1"
    assert response.json()["reason_code"] == "request.invalid"


def test_conflicting_idempotency_payload_returns_409(experiment, now) -> None:  # type: ignore[no-untyped-def]
    api, _runs = client(now)
    headers = {"Idempotency-Key": "same-key"}
    assert (
        api.post("/v1/ingestion-runs", json=request_body(experiment), headers=headers).status_code
        == 202
    )
    changed = experiment.model_copy(update={"parameters": {"retrieval_k": 999}})
    response = api.post("/v1/ingestion-runs", json=request_body(changed), headers=headers)
    assert response.status_code == 409
    assert response.json()["reason_code"] == "run.idempotency_conflict"


def test_domain_error_emits_structured_http_failure(experiment, now, caplog) -> None:  # type: ignore[no-untyped-def]
    api, _runs = client(now)
    headers = {"Idempotency-Key": "same-key"}
    api.post("/v1/ingestion-runs", json=request_body(experiment), headers=headers)
    changed = experiment.model_copy(update={"parameters": {"changed": True}})
    with caplog.at_level(logging.WARNING):
        response = api.post("/v1/ingestion-runs", json=request_body(changed), headers=headers)
    events = [record for record in caplog.records if getattr(record, "event", None) == "http.error"]
    assert response.status_code == 409
    assert events[-1].status_code == 409
    assert events[-1].outcome == "failure"
    assert events[-1].reason_code == "run.idempotency_conflict"
    assert events[-1].trace_id == response.headers["x-trace-id"]


class ExplodingRuns:
    def get(self, _run_id: str, _expected_type: object) -> None:
        raise RuntimeError("private request body")


def test_internal_error_is_structured_and_diagnostic_content_is_redacted(now, caplog) -> None:  # type: ignore[no-untyped-def]
    api, _runs = client(now)
    api.app.state.services = Services(
        runs=ExplodingRuns(),  # type: ignore[arg-type]
        readiness=ReadinessApplicationService(()),
    )
    non_raising_api = TestClient(api.app, raise_server_exceptions=False)
    with caplog.at_level(logging.ERROR):
        response = non_raising_api.get("/v1/ingestion-runs/boom")
    assert response.status_code == 500
    event = next(
        record for record in caplog.records if getattr(record, "event", None) == "http.error"
    )
    assert event.status_code == 500
    assert event.reason_code == "internal.error"
    assert "test_api.py" in event.stack
    assert "private request body" not in caplog.text


def test_throwing_readiness_dependency_returns_precise_503(now) -> None:  # type: ignore[no-untyped-def]
    api, runs = client(now)
    api.app.state.services = Services(
        runs=runs,
        readiness=ReadinessApplicationService((Check("sqlite", True), ThrowingCheck())),
    )
    response = api.get("/readyz")
    assert response.status_code == 503
    assert response.json()["dependencies"]["sqlite"]["ready"] is True
    assert response.json()["dependencies"]["throwing"] == {
        "ready": False,
        "detail": "RuntimeError: dependency check failed",
    }
