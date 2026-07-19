"""Stable HTTP error representation and application-to-HTTP mapping."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from rag_app.domain.errors import DomainError, RunNotFoundError
from rag_app.observability.context import current_trace_id
from rag_app.observability.logging import emit_event

logger = logging.getLogger(__name__)


class ErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = "error-v1"
    reason_code: str
    message: str
    trace_id: str


def _response(
    status: int,
    reason_code: str,
    message: str,
    *,
    exception: BaseException | None = None,
) -> JSONResponse:
    emit_event(
        logger,
        "http.error",
        level=logging.ERROR if status >= 500 else logging.WARNING,
        stage="http_error",
        outcome="failure",
        status_code=status,
        reason_code=reason_code,
        exception=exception,
    )
    body = ErrorBody(reason_code=reason_code, message=message, trace_id=current_trace_id())
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RunNotFoundError)
    async def not_found(_request: Request, exc: RunNotFoundError) -> JSONResponse:
        return _response(404, exc.reason_code, str(exc), exception=exc)

    @app.exception_handler(DomainError)
    async def domain_error(_request: Request, exc: DomainError) -> JSONResponse:
        return _response(409, exc.reason_code, str(exc), exception=exc)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        return _response(422, "request.invalid", "request validation failed", exception=_exc)

    @app.exception_handler(Exception)
    async def internal_error(_request: Request, _exc: Exception) -> JSONResponse:
        return _response(
            500,
            "internal.error",
            "an internal error occurred",
            exception=_exc,
        )
