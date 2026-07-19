# RAG application foundation

Phase 0 provides reproducible contracts, configuration, immutable manifests, queued run
metadata, readiness checks, structured logs, and a thin FastAPI adapter. It intentionally does
not ingest data, execute evaluations, retrieve documents, or generate answers.

## Prerequisites

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/)
- Docker with at least 2 GB available to OpenSearch (only for the Compose runtime)

## Install and verify

```bash
uv sync --frozen --extra dev
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```

Copy `.env.example` to `.env` only when overrides are needed. Inspect the effective,
secret-redacted settings with `uv run rag-inspect-config`.

## Run locally

```bash
docker compose up -d
curl http://localhost:8000/healthz
curl http://localhost:8000/readyz
docker compose down
```

The API stores operational metadata in `var/metadata/rag.sqlite3` and immutable manifests in
`var/artifacts/`. These locations are separate and ignored by Git. `POST` run endpoints only
persist `queued` records; no worker exists in Phase 0.

Without Docker, start the API with `uv run rag-api`. Liveness remains healthy if OpenSearch is
down; readiness identifies the unavailable dependency.

## API

- `GET /healthz`
- `GET /readyz`
- `POST/GET /v1/ingestion-runs[/{run_id}]`
- `POST/GET /v1/evaluation-runs[/{run_id}]`

OpenAPI is available at `/docs`. No query or trace-retrieval endpoint is advertised.

## Troubleshooting

If OpenSearch remains unhealthy on Linux, ensure `vm.max_map_count=262144`. On macOS, increase
the Docker Desktop memory allocation. Removing `var/` resets local application state; it does
not affect the named OpenSearch volume.

