"""FastAPI application factory."""

from fastapi import FastAPI

from rag_app.api.dependencies import Services, compose_services
from rag_app.api.errors import register_error_handlers
from rag_app.api.middleware import TraceMiddleware
from rag_app.api.routes import health, runs
from rag_app.config.loader import load_settings
from rag_app.config.models import Settings
from rag_app.observability.logging import configure_logging


def create_app(settings: Settings | None = None, services: Services | None = None) -> FastAPI:
    resolved_settings = settings or load_settings()
    configure_logging(
        resolved_settings.observability.log_level,
        resolved_settings.observability.max_field_length,
    )
    app = FastAPI(
        title="RAG Application",
        version="0.1.0",
        description="Phase 0 queued-run and readiness adapter",
    )
    app.state.settings = resolved_settings
    app.state.services = services or compose_services(resolved_settings)
    app.add_middleware(TraceMiddleware)
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(runs.router)
    return app
