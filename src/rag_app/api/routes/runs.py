"""Thin queued-run HTTP adapter."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Response, status
from pydantic import BaseModel, ConfigDict

from rag_app.api.dependencies import Services, get_services
from rag_app.application.runs import CreateRunCommand
from rag_app.domain.experiments import ExperimentConfig
from rag_app.domain.indexes import ResolvedIndexReference
from rag_app.domain.runs import RunRecord, RunType

router = APIRouter(prefix="/v1", tags=["runs"])


class CreateRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    experiment: ExperimentConfig
    resolved_index: ResolvedIndexReference | None = None


class RunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["run-response-v1"] = "run-response-v1"
    run: RunRecord


def _create(
    run_type: RunType,
    request: CreateRunRequest,
    idempotency_key: str,
    response: Response,
    services: Services,
) -> RunResponse:
    record = services.runs.create(
        CreateRunCommand(
            run_type=run_type,
            idempotency_key=idempotency_key,
            experiment=request.experiment,
            resolved_index=request.resolved_index,
        )
    )
    response.status_code = status.HTTP_202_ACCEPTED
    response.headers["Location"] = f"/v1/{run_type.value}-runs/{record.run_id}"
    return RunResponse(run=record)


@router.post("/ingestion-runs", response_model=RunResponse, status_code=202)
def create_ingestion_run(
    request: CreateRunRequest,
    response: Response,
    services: Annotated[Services, Depends(get_services)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=256)],
) -> RunResponse:
    return _create(RunType.INGESTION, request, idempotency_key, response, services)


@router.get("/ingestion-runs/{run_id}", response_model=RunResponse)
def get_ingestion_run(
    run_id: str, services: Annotated[Services, Depends(get_services)]
) -> RunResponse:
    return RunResponse(run=services.runs.get(run_id, RunType.INGESTION))


@router.post("/evaluation-runs", response_model=RunResponse, status_code=202)
def create_evaluation_run(
    request: CreateRunRequest,
    response: Response,
    services: Annotated[Services, Depends(get_services)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=256)],
) -> RunResponse:
    return _create(RunType.EVALUATION, request, idempotency_key, response, services)


@router.get("/evaluation-runs/{run_id}", response_model=RunResponse)
def get_evaluation_run(
    run_id: str, services: Annotated[Services, Depends(get_services)]
) -> RunResponse:
    return RunResponse(run=services.runs.get(run_id, RunType.EVALUATION))
