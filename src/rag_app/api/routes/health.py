"""Liveness and dependency-readiness routes."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response, status

from rag_app.api.dependencies import Services, get_services

router = APIRouter(tags=["health"])


@router.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "live", "schema_version": "health-v1"}


@router.get("/readyz")
def readiness(
    response: Response, services: Annotated[Services, Depends(get_services)]
) -> dict[str, Any]:
    result = services.readiness.check()
    if not result.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"schema_version": "readiness-v1", **result.model_dump(mode="json")}
