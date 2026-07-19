# ADR 0001: Phase 0 architectural boundaries

Status: accepted

- FastAPI, future evaluation code, CLI tools, and workers are peer inbound adapters over shared
  application services. A future `QueryApplicationService` is the sole query entry point.
- Query rewriting and strategy selection precede retrieval. HyDE is generated retrieval context,
  hierarchy is a retrieval strategy, and multi-hop is a bounded retrieval/reranking loop.
- Exact source bytes are stored immutably before parsing; parsed structures never replace them.
- Benchmark corpus, queries, relevance judgments, and expected answers remain separate streams.
- Index builds are immutable. Validation precedes atomic alias promotion; a request resolves the
  alias once and records the exact physical index, enabling rollback to a prior validated build.
- SQLite stores operational run metadata and artifact references. Artifacts, search indexes,
  telemetry, and caches use separate interfaces and stores.
- Long-running endpoints create queued work and return. Executors are introduced only with real
  ingestion or evaluation capabilities.

