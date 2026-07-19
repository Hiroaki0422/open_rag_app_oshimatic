# Coding Agent Prompt: Revise Phase 0 Before Approval

Phase 0 is close, and its baseline checks currently pass, but it is **not approved yet**. Fix the bounded foundation issues below. Do not start Phase 1 and do not add ingestion, indexing, retrieval, routing, generation, evaluation-runner, worker, or query-service implementations.

## Context and authoritative documents

Use these as the implementation contract:

- `docs/RAG_APPLICATION_DEVELOPMENT_PLAN.md`
- `docs/PHASE_0_IMPLEMENTATION_PLAN.md`
- `docs/REPOSITORY_STRUCTURE_PROPOSAL.md`
- `docs/adr/0001-phase-0-boundaries.md`

Preserve the existing architectural direction:

- FastAPI remains a thin inbound adapter over framework-neutral application services.
- Long-running endpoints create queued work and return `202`.
- SQLite stores operational metadata and artifact references only.
- Manifests remain immutable artifacts.
- No unimplemented API endpoints or empty later-phase packages.

## Baseline status

The following currently pass:

```text
uv sync --frozen --extra dev
ruff format --check .
ruff check .
mypy src
pytest tests/unit tests/golden       # 39 passed
pytest -m integration                # 4 passed
docker compose config --quiet
```

Keep them passing while adding the missing regression tests below.

## Required revisions

### 1. Enforce run-state invariants on every construction and transition

`RunRecord.transition()` currently uses an unvalidated `model_copy(update=...)`. This allows a transition to produce a record whose `updated_at` predates `created_at`, and it allows a non-failed state to carry a failure reason.

Correct the model and transition behavior so that:

- `updated_at >= created_at` always holds.
- A transition timestamp cannot precede the current record's `updated_at`.
- `failure_reason_code` is required only for `FAILED` and rejected/cleared for other states.
- Lease owner/expiration fields have a consistent invariant.
- All transition outputs are fully validated rather than trusting `model_copy(update=...)`.
- Invalid direct `RunRecord` construction is rejected as well as invalid transitions.

Add tests for backward timestamps, failure reasons on non-failed states, malformed lease pairs, and all valid/invalid lifecycle edges.

### 2. Make idempotency payload-aware and race-safe

The same `(run_type, idempotency_key)` currently returns the old run even when the caller submits a different experiment. That silently accepts a request that was never scheduled.

Implement these semantics:

- Reusing a key with the same canonical request fingerprint returns the existing run.
- Reusing a key with a different fingerprint raises a stable domain error such as `IdempotencyConflictError`.
- FastAPI maps that conflict to `409` with the normal machine-readable error body.
- The same behavior holds when two writers race and the SQLite unique constraint resolves the conflict.
- Persist the request fingerprint explicitly; do not infer equality from mutable or incomplete fields.

Add unit, SQLite integration, concurrent/race, and API tests for matching and conflicting reuse.

### 3. Make experiment configuration typed and enforce protected split usage

`ExperimentConfig.feature_flags` is currently `dict[str, bool]`, so misspelled or unknown capabilities are accepted. It also stores only `dataset_version`, so the Phase 0 rule preventing test-split tuning cannot be enforced.

Revise the experiment contract to:

- Use a strict typed feature/configuration snapshot with unknown fields forbidden.
- Represent dataset name, version, and split explicitly.
- Represent run/evaluation intent explicitly enough to distinguish tuning/development from final evaluation.
- Reject protected test splits for tuning commands while allowing an explicit final-evaluation mode.
- Require the relevant parser, chunker, contextualizer, embedding, reranker, generator, and prompt/provider versions when their corresponding capabilities are enabled.
- Continue rejecting secrets anywhere in the persisted configuration.
- Keep every unimplemented Phase 0 capability disabled in runtime settings.

Update the example experiment JSON and golden manifest fixture intentionally. Add tests for typoed flags, missing capability versions, nested secrets, and test-split tuning rejection.

### 4. Complete exact resolved-index identity contracts

`ResolvedIndexReference` currently records a logical reference, physical name, generic `index_version`, and timestamp. The architecture contract requires enough immutable identity to replay a query after an alias changes.

Include and validate at least:

- Logical index/alias
- Exact physical index name
- Index-manifest hash or immutable manifest reference
- Corpus snapshot version/hash
- Embedding model/version used to build the index
- Resolution timestamp

Use typed digest/reference fields rather than free-form checksum strings. Ensure `QueryResult` and the experiment/evaluation manifest contracts carry this complete resolved reference. Keep index activation itself out of Phase 0.

Add round-trip and negative tests proving that an alias alone or an incomplete resolved reference is not accepted.

### 5. Strengthen answer/citation domain invariants

`QueryResult` currently accepts a non-abstaining answer with zero evidence and zero citations. For this RAG contract:

- A non-abstaining answer must contain evidence and at least one valid citation.
- Every citation must reference evidence included in the result.
- Citation IDs must be unique.
- Claim-to-citation mapping must be representable and validated.
- An abstention cannot masquerade as an answered result; define whether evidence is allowed on abstention and enforce that policy.
- Generated contextual headers and HyDE text must remain ineligible as evidence.

Add explicit tests showing that an uncited answer is rejected.

### 6. Finish the observability and readiness failure paths

Unhandled and domain exceptions are mapped to HTTP responses but are not emitted as structured diagnostic events. Also, `observability.max_field_length` is defined but not wired into event emission.

Revise this so that:

- HTTP/application failures emit structured events with trace ID, stage, outcome, HTTP status, and stable reason code.
- Internal exceptions retain useful diagnostic stack information without logging request bodies, source content, prompts, secrets, or provider payloads.
- The configured maximum field length is actually applied; remove ineffective/dead configuration.
- Direct application-service calls obtain a bounded trace context instead of accidentally reusing a generated context forever.
- A dependency-health adapter that raises is isolated and reported as a dependency-specific readiness failure (`503`), not a generic API `500`.

Add tests for domain/internal exception events, redaction, configured truncation, direct-call trace isolation, and throwing readiness adapters.

### 7. Complete migration, packaging, Docker-context, and CI gates

The current migration method hardcodes `001_runs.sql`, and CI does not start the pinned OpenSearch service or perform the planned secret/large-artifact checks.

Make these corrections:

- Discover and apply ordered, versioned SQL migrations transactionally, recording each applied version.
- Add a migration test that starts at version 1 and upgrades through a new migration required by the idempotency fingerprint.
- Verify the built wheel contains and can execute migrations from a clean installation.
- Add `.dockerignore` so `.git`, `.venv`, caches, local data, artifacts, notebooks, secrets, and build outputs are not sent in the Docker build context.
- In CI, start the pinned OpenSearch service and run at least one real readiness integration test against it.
- Add a Docker build/config smoke gate.
- Add automated checks for accidentally committed secrets and oversized/generated artifacts. Keep full datasets out of CI.

Do not weaken the unit/integration distinction: normal application-service tests must remain independent of OpenSearch and Docker.

## Required verification

Run and report all of the following after the revisions:

```bash
uv sync --frozen --extra dev
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest tests/unit tests/golden
uv run pytest -m integration
uv build
docker compose config --quiet
docker compose build api
```

Also run the live OpenSearch readiness test using the same pinned image used by CI.

## Completion response

Return:

1. A concise summary grouped by the seven revisions above.
2. The final test/check counts and command outcomes.
3. Any deliberately deferred work, with confirmation that it belongs after Phase 0.
4. The final repository status showing only intentional source changes.

Do not create a Phase 1 plan; Phase 1 will be planned only after this revision receives review approval.
