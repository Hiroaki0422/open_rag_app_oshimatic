FROM python:3.12.11-slim
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.8.3 /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"
CMD ["rag-api"]

