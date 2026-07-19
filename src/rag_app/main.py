"""ASGI and console entry points."""

import uvicorn

from rag_app.api.app import create_app
from rag_app.config.loader import load_settings

app = create_app()


def run() -> None:
    settings = load_settings()
    uvicorn.run(
        "rag_app.main:app",
        host=settings.api.host,
        port=settings.api.port,
        reload=False,
    )
