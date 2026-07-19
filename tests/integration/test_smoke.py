import pytest
from fastapi.testclient import TestClient

from rag_app.api.app import create_app
from rag_app.api.dependencies import compose_services
from rag_app.application.runs import CreateRunCommand
from rag_app.config.loader import load_settings
from rag_app.domain.runs import RunType

pytestmark = pytest.mark.integration


def test_reproducibility_and_adapter_independence(settings, experiment) -> None:  # type: ignore[no-untyped-def]
    resolved = load_settings().model_copy(
        update={"metadata": settings.metadata, "artifacts": settings.artifacts}
    )
    services = compose_services(resolved)
    first = services.runs.create(
        CreateRunCommand(
            run_type=RunType.INGESTION, idempotency_key="direct-one", experiment=experiment
        )
    )
    second = services.runs.create(
        CreateRunCommand(
            run_type=RunType.INGESTION, idempotency_key="direct-two", experiment=experiment
        )
    )
    assert first.run_id != second.run_id
    assert first.manifest == second.manifest
    assert services.runs.get(first.run_id) == first

    api = TestClient(create_app(resolved, services))
    response = api.get(f"/v1/ingestion-runs/{first.run_id}")
    assert response.status_code == 200
    assert response.json()["run"]["run_id"] == first.run_id
    assert response.json()["run"]["status"] == "queued"
