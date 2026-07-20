# Phase 1 Implementation Plan: Dataset Adapter Framework

**Status:** Proposed for review  
**Parent plan:** [RAG Application Development Plan](./RAG_APPLICATION_DEVELOPMENT_PLAN.md)  
**Architecture:** [Repository Structure and Architecture Proposal](./REPOSITORY_STRUCTURE_PROPOSAL.md)  
**Foundation:** [Phase 0 Implementation Plan](./PHASE_0_IMPLEMENTATION_PLAN.md)

## 1. Objective

Implement a deterministic dataset-adapter layer that turns heterogeneous benchmark sources into
the existing, separate canonical streams:

- `CorpusDocument`
- `BenchmarkQuery`
- `RelevanceJudgment`
- `ExpectedAnswer`

Phase 1 makes local benchmark data inspectable and reproducible without coupling dataset formats
to ingestion, retrieval, generation, or evaluation execution. It proves the framework first with
BEIR, then adds the remaining adapters only when their source and cross-stream validation gates
pass.

## 2. Evidence Used for This Plan

The following local evidence was confirmed on 2026-07-20:

- `data/analysis_outputs/` contains nine analysis artifacts totaling approximately 7.3 MiB.
- The machine-readable report is
  `data/analysis_outputs/rag_dataset_build_readiness_report.json`, SHA-256
  `c8fa04005cc5bcade4ff9c9c05c5f9bef1fb5c9617651d22900695c1e8e5507d`.
- The report describes source archive
  `/content/drive/MyDrive/rag_data/rag_dataset_subsets.zip`, SHA-256
  `aaa0a4aead175da0a63d0039cd9866245124ef81ada102588151c73735dd1b2a`, size
  1,110,728,623 bytes.
- The analysis covered 1,095 files and 191,522 loaded rows, capped at 5,000 rows per file.
- The saved analysis notebook is
  `notebooks/data_analysis/rag_dataset_build_readiness_analysis_colab.ipynb`.
- The collection and portable-subset workflow is
  `notebooks/data_collection/rag_public_dataset_collector_colab.ipynb`.

The source archive and extracted benchmark records are not currently present under `data/raw/`.
Phase 1 implementation therefore begins by verifying or materializing the exact source snapshot;
it must not infer that the analysis outputs themselves are adapter inputs.

### 2.1 Findings that directly affect implementation

| Finding | Phase 1 consequence |
| --- | --- |
| 1,020 files had no confident asset inference | Heuristic inference is diagnostic only; every adapter uses an explicit reviewed schema map. |
| 504 field/file combinations had mixed types | Readers report typed coercion failures with file and row location; no silent stringification. |
| 606 field/file combinations were below 95% complete | Missing-value policy is explicit per adapter and field. |
| 36 files exceeded 5% exact duplicates | Adapters preserve source fidelity and report duplicates; Phase 2 owns document deduplication. Conflicting duplicate IDs are errors now. |
| 14 document fields exceeded 512 approximate tokens at p95 | Preserve complete source text and locators. Chunking remains Phase 2. |
| Estimated 512-token subsets produce about 230,889 chunks across analyzed groups | Carry this into Phase 2 capacity planning; do not select an embedding model in Phase 1. |
| Token counts use `ceil(characters/4)` | Do not treat them as tokenizer measurements. Recalculate in Phase 2. |
| The first archive directory was classified as `files`, `huggingface`, or `unclassified` | Dataset identity must come from an explicit source manifest/path rule, not the first path segment. |

### 2.2 Adapter-specific readiness

| Adapter | Evidence | Decision |
| --- | --- | --- |
| BEIR | Five compact collections have separate corpus, queries, and qrels files. Corpus IDs/text are complete in most samples; qrel mapping was only medium-confidence because IDs require explicit schema rules. | First vertical slice. Implement SciFact first, then ArguAna, FiQA, NFCorpus, and TREC-COVID. |
| Natural Questions | One nested validation JSONL contains question, document HTML/tokens, annotations, long-answer candidates, and answer spans. The heuristic incorrectly classified it primarily as a corpus stream. | Implement only after a reviewed nested-field mapping and locator policy. Decompose combined rows into separate streams. |
| FEVER | Claims include IDs, labels, evidence wiki URLs, and sentence IDs. The safe collection omitted `wiki_pages`. | Implement claims/query/judgment/answer mapping, but fail retrieval-readiness until the exact referenced corpus is available. Never fabricate corpus documents. |
| RGB | Eight sampled files loaded with zero rows and were marked manual review. | Fix or replace the portable-sampling path and review the official schema before implementing the adapter. Zero-row success is invalid. |
| HotpotQA | Train/validation samples contain question, answer, contexts, and supporting facts; context p95 is about 2,023 approximate tokens. | Wave 2 after the common framework; preserve supporting-fact locators and combined-record provenance. |
| MuSiQue | Multiple train/dev/test combined files are present and large, with answer aliases and multi-hop structure. | Wave 2 after explicit file selection; ignore repository metadata files as benchmark assets. |
| MultiHop-RAG | Separate corpus and benchmark JSON samples are available. | Wave 2 after schema and join validation. Exclude Hugging Face cache metadata. |
| RAGBench | Collected as repository content with heterogeneous domain configurations. | Wave 3 after a source inventory distinguishes benchmark data from repository/cache files. |
| Open RAG Benchmark | Hundreds of PDF-derived files dominate the manual-review count; many portable samples are zero bytes. | Wave 3 inventory only. PDF parsing and multimodal behavior remain later phases. |
| CRAG | The portable task sample is zero bytes; dynamic web/KG semantics require a federated provider boundary later. | Wave 3 schema adapter only after sample repair. Do not model CRAG as a static OpenSearch corpus. |

## 3. Scope Guardrail

Phase 1 includes only:

- Dataset source descriptors, cache manifests, checksums, and split-role metadata
- Local prepared-source readers with bounded, line-aware errors
- A framework-neutral `DatasetAdapter` protocol
- Separate corpus/query/judgment/answer iterators
- Explicit dataset-family schema maps
- Cross-stream validation and machine-readable validation reports
- Deterministic, license-reviewed or synthetic smoke fixtures
- A local inspection/validation CLI
- Adapter unit, golden, contract, and local integration tests

Phase 1 does **not** implement:

- Document parsing or chunking
- Raw-source ingestion into the Phase 2 artifact flow
- Embeddings or OpenSearch indexing
- Retrieval, routing, HyDE, hierarchy, or multi-hop execution
- Generation or citation checking
- An evaluation runner or `QueryApplicationService`
- Workers, queues, or new long-running HTTP endpoints
- PDF layout extraction, multimodal processing, or CRAG web/KG providers

## 4. Fixed Design Decisions

### 4.1 Separate streams remain non-negotiable

The adapter protocol exposes four independent iterators. A combined source record such as Natural
Questions, FEVER, HotpotQA, or MuSiQue may feed multiple iterators, but it is never emitted as one
combined ingestion object. `BenchmarkExample` remains an evaluation-only view.

### 4.2 Prepared sources are immutable and explicit

Adapters read a prepared local source described by a `DatasetSourceManifest`. Downloading or
extracting is handled by a separate acquisition boundary so that adapter tests never access the
network. Every manifest records:

- Dataset family and upstream identifier
- Upstream version/revision and adapter version
- Archive and file SHA-256 digests and byte lengths
- Media type and relative path
- Explicit split name and `SplitRole`
- License/provenance review status
- Sampling method, seed, row cap, and parent source when applicable

The manifest identity excludes absolute machine paths, timestamps, credentials, and cache
locations. Paths inside a prepared snapshot are relative and traversal-safe.

### 4.3 Split protection uses metadata, never names

Phase 1 reuses one canonical `SplitRole` for dataset and experiment contracts. Every adapter maps
each upstream split explicitly to `TRAIN`, `DEVELOPMENT`, or `TEST`. Names such as `validation`,
`paper_test`, `blind_test`, or `challenge` have no policy meaning without the role. Tuning and
development selection of `TEST` remains rejected by the Phase 0 experiment invariant.

### 4.4 Validation fails closed

Adapters do not silently skip malformed rows. Validation reports may classify individual records
as errors, but an adapter is not `ready` when required streams are missing, IDs conflict, qrels
reference absent records, protected split metadata is absent, or the source checksum differs.

Exact duplicate content is reported rather than removed. An identical duplicate external ID may
be collapsed only under an explicit adapter rule and count; the same ID with different content is
always an error.

### 4.5 Local data and portable results stay out of Git

The repository ignores `/data/` in full. Raw archives, extracted data, analysis outputs, cache
manifests, and generated reports remain local. CI uses small reviewed fixtures under
`datasets/smoke/`. If redistribution is not permitted, use synthetic schema-equivalent fixtures
and store only provenance/checksum metadata.

## 5. Phase 1 Materialized Repository

Create modules only with working behavior and tests. The expected completed shape is:

```text
src/rag_app/
├── datasets/
│   ├── __init__.py
│   ├── contracts.py          # Adapter/source/validation contracts
│   ├── ports.py              # DatasetAdapter and source-acquisition protocols
│   ├── readers.py            # Bounded JSON/JSONL/CSV/TSV readers
│   ├── validation.py         # Shared cross-stream validation
│   ├── registry.py           # Explicit adapter registration, no dynamic imports
│   ├── cli.py                # rag-inspect-dataset inbound adapter
│   ├── beir.py
│   ├── natural_questions.py
│   ├── fever.py
│   ├── rgb.py
│   ├── hotpotqa.py
│   ├── musique.py
│   ├── multihop_rag.py
│   ├── ragbench.py
│   ├── open_rag_benchmark.py
│   └── crag.py
├── domain/
│   └── benchmarks.py         # Extended/versioned only where canonical fields require it
└── infrastructure/
    └── datasets/
        └── local.py          # Prepared local snapshot/cache implementation

datasets/
├── manifests/                # Non-secret fixture/provenance manifests only
└── smoke/                    # Licensed or synthetic deterministic fixtures

tests/
├── unit/datasets/
├── golden/datasets/
└── integration/datasets/
```

An adapter module is added only in the increment that implements and tests it. Do not create empty
Wave 2 or Wave 3 modules during framework bootstrap.

## 6. Application Contracts

The protocol should be equivalent to:

```python
class DatasetAdapter(Protocol):
    def descriptor(self) -> DatasetDescriptor: ...
    def source_manifest(self) -> DatasetSourceManifest: ...
    def iter_corpus_documents(self) -> Iterator[CorpusDocument]: ...
    def iter_queries(self, split: SplitSelection) -> Iterator[BenchmarkQuery]: ...
    def iter_relevance_judgments(
        self, split: SplitSelection
    ) -> Iterator[RelevanceJudgment]: ...
    def iter_expected_answers(self, split: SplitSelection) -> Iterator[ExpectedAnswer]: ...
    def official_metrics(self) -> tuple[MetricDescriptor, ...]: ...
    def validate(self) -> DatasetValidationReport: ...
```

Contract details:

- `DatasetDescriptor` gains explicit split role and adapter/source versions through a deliberate
  schema increment.
- Corpus, query, judgment, and answer IDs retain upstream IDs plus dataset namespace; IDs from
  different asset classes are never interchangeable merely because their source strings match.
- Every normalized record carries source provenance sufficient to find the source file and row.
- Evidence locators are typed for document, sentence, token, or byte spans where the source
  provides them.
- Expected labels and natural-language answers remain distinguishable.
- Iteration order is deterministic and documented. Hash identities never depend on filesystem
  discovery order.
- `official_metrics()` describes metrics; it does not run evaluation in Phase 1.

## 7. Work Breakdown

### P1.1 — Protect local data and freeze the evidence snapshot

1. Ignore `/data/` and verify representative raw, cache, and analysis paths with
   `git check-ignore`.
2. Add local storage documentation for `data/raw/`, `data/prepared/`, `data/cache/`, and
   `data/analysis_outputs/`.
3. Verify an incoming archive against the report's recorded SHA-256 before extraction.
4. Reject archive traversal, symlinks escaping the target, duplicate member paths, and unexpected
   decompressed-size limits.
5. Generate an immutable prepared-source manifest from relative file paths and exact bytes.
6. Record that the current analysis is capped and heuristic; never promote its inferred mappings
   directly into production adapter rules.

**Done when:** Local data cannot appear in Git status, the exact analyzed source can be verified,
and a checksum mismatch stops preparation.

### P1.2 — Define dataset contracts and the adapter protocol

1. Add versioned source-manifest, file-reference, split-selection, metric-descriptor, validation
   issue, and validation-report contracts.
2. Consolidate `SplitRole` into a shared domain location used by both dataset and experiment
   contracts; do not duplicate the enum.
3. Extend benchmark descriptors only through explicit schema increments and golden fixtures.
4. Define stable reason codes for checksum, parsing, duplicate ID, missing value, orphan qrel,
   missing corpus, unsupported schema, protected split, and license/provenance failures.
5. Keep all protocols independent of Hugging Face, pandas, FastAPI, OpenSearch, and provider SDKs.

**Tests:** construction/round-trip, invalid digests, missing split roles, unknown fields, stable JSON
Schema, namespace separation, and import boundaries.

### P1.3 — Implement prepared-source readers and cache manifests

1. Implement streaming UTF-8 JSONL, JSON, CSV, and TSV readers with configurable row and byte
   limits.
2. Report file path, row number, and stable reason code without logging record content.
3. Keep original values available to adapters; coercion is adapter-specific and explicit.
4. Verify every file before reading and fail if bytes change after manifest creation.
5. Write manifests atomically and immutably using canonical serialization.
6. Never import or download data during module import, tests, or API startup.

**Tests:** malformed rows, invalid UTF-8, quoted TSV/CSV values, empty files, checksum changes,
path traversal, deterministic order, atomic writes, and bounded record sizes.

### P1.4 — Implement shared validation

Validation produces counts and issues separately for each asset stream:

- Empty or malformed IDs/text/answers
- Duplicate and conflicting IDs
- Exact duplicate content rates
- Missing expected streams
- Qrels referencing absent query or corpus IDs
- Expected answers referencing absent queries
- Evidence locator validity
- Unknown labels or relevance values
- Split counts and explicit split roles
- Unsupported records and adapter skip counts
- Source/adapter/manifest identities

Validation severity is dataset-specific but explicit. A report includes `ready_for_retrieval_eval`
and `ready_for_answer_eval` separately; aggregate directory-level readiness from the analysis is
not sufficient.

**Done when:** A broken join or zero-row required stream cannot report ready.

### P1.5 — Deliver the BEIR vertical slice

Implement in this order:

1. **SciFact:** smallest clear corpus/query/qrel vertical; treat train as `TRAIN` and test as
   `TEST`. It is suitable for contract validation but not test-split tuning.
2. **FiQA:** use the explicit dev qrels as `DEVELOPMENT`; this becomes the first tuning-capable
   smoke path.
3. **NFCorpus:** add train/dev/test mappings and validate qrel joins.
4. **ArguAna:** test-only in the analyzed subset; final-evaluation role only.
5. **TREC-COVID:** handle query text explicitly (`metadata.query` where required) and validate the
   incomplete corpus-text rate observed in the sample.

BEIR rules are explicit: corpus `_id` is a document ID, query `_id` is a query ID, and qrels map
`query-id`, `corpus-id`, and `score`. The analysis heuristic's classification of query files as
corpus documents must not be reused.

**Tests:** official-shaped synthetic fixtures, all cross-stream joins, deterministic counts,
development/test role enforcement, malformed qrels, and one 25–100 query CI smoke fixture per
selected collection.

**Done when:** Five collection adapters emit the same canonical types and their validation reports
identify which collections can be used for development versus final evaluation.

### P1.6 — Complete Wave 1 with gated NQ, FEVER, and RGB adapters

**Natural Questions**

1. Map one nested validation record to a query, a stable corpus document, judgments/evidence, and
   expected answers.
2. Preserve URL/title and token/byte offsets; strip or parse HTML only in Phase 2.
3. Define stable corpus identity for repeated documents and report conflicting versions.
4. Represent long answer, short answers, yes/no answer, and unanswerable cases without conflation.
5. Mark the collected validation data `DEVELOPMENT`; do not infer role from its filename.

**FEVER**

1. Map claim IDs, labels, evidence wiki URLs, annotation IDs, and sentence IDs explicitly.
2. Preserve multiple evidence sets rather than flattening them into independent false alternatives.
3. Treat `unlabelled_*` records as having no expected answer rather than empty labels.
4. Require the matching Wikipedia corpus/source version before declaring retrieval-ready.
5. Mark paper/test splits `TEST`; only labelled development data is tuning-capable.

**RGB**

1. Repair portable sampling so the eight analyzed zero-row files produce valid records or an
   explicit unsupported-source error.
2. Review English and Chinese schemas independently.
3. Preserve the benchmark mode (noise, rejection, integration, counterfactual/refinement) in
   typed metadata.
4. Do not fabricate indexed corpus documents when the benchmark supplies contexts rather than a
   retrievable corpus; report the supported evaluation mode explicitly.

**Done when:** No Wave 1 adapter relies on a heuristic field guess, zero-row input cannot pass,
and missing FEVER corpus data is visible as a readiness blocker rather than hidden.

### P1.7 — Add Wave 2 adapters

After Wave 1 framework review:

- **HotpotQA:** decompose combined rows, retain supporting-fact title/sentence locators, and
  preserve context paragraphs without chunking.
- **MuSiQue:** select only official benchmark files, preserve 2–4 hop decomposition/evidence, and
  exclude repository metadata/answer-alias files from corpus iteration unless explicitly needed.
- **MultiHop-RAG:** map its separate corpus and question records, preserving document metadata and
  complete evidence sets.

Validation adds complete evidence-set coverage and multi-document join checks, but does not run
multi-hop retrieval.

### P1.8 — Add Wave 3 adapters behind readiness gates

- **RAGBench:** inventory official domain configurations and distinguish supplied contexts from
  independently retrievable corpora.
- **Open RAG Benchmark:** create a source catalog and question/answer adapter only for valid
  text-extractable metadata. Keep PDF parsing and table/image support deferred.
- **CRAG:** repair the zero-byte sample and model its static benchmark records without implementing
  web/KG retrieval. Record that its future dynamic sources require provider adapters.

No Wave 3 adapter is considered complete from the current aggregate analysis alone. Each requires
an adapter-specific schema report and non-empty smoke fixture first.

### P1.9 — Add inspection CLI, CI, and reproducibility demonstration

1. Add `rag-inspect-dataset` commands to list adapters, print a secret-safe source manifest, and
   validate one prepared source.
2. Output machine-readable JSON with adapter/source IDs, per-stream counts, readiness flags, and
   stable issues.
3. Run unit/golden tests on every change and local-file integration tests without network access.
4. Add CI checks proving `/data/` remains ignored and no raw archives or generated reports are
   committed.
5. Validate 25–100 query smoke fixtures per completed adapter without downloading a full dataset.
6. Demonstrate two reads of the same snapshot produce byte-identical normalized streams and
   manifest/report identities.
7. Demonstrate a one-byte source change alters the source identity and prevents stale-cache reuse.

## 8. Adapter Delivery Order and Review Gates

```text
Framework/contracts
  -> readers + manifests
  -> validation
  -> BEIR SciFact vertical
  -> remaining compact BEIR collections
  -> Natural Questions
  -> FEVER claims + corpus readiness gate
  -> RGB sample repair + adapter
  -> Wave 1 review
  -> HotpotQA / MuSiQue / MultiHop-RAG
  -> Wave 2 review
  -> RAGBench / Open RAG Benchmark / CRAG readiness work
```

Each adapter is a separate review increment containing its source mapping, fixtures, validation
rules, tests, and documentation. Do not merge all dataset families into one large adapter change.

## 9. Verification Matrix

| Requirement | Evidence |
| --- | --- |
| Local datasets never enter Git | Root `/data/` ignore rule plus `git check-ignore` CI test |
| Source identity is reproducible | Archive/file checksum and canonical source-manifest golden tests |
| Dataset formats do not leak inward | Every adapter emits only provider-neutral domain contracts |
| Asset streams remain separate | Independent iterator and type tests; no `BenchmarkExample` ingestion path |
| Protected splits cannot be tuned | Explicit `SplitRole` mappings and negative experiment-selection tests |
| IDs join correctly | Orphan query/document/answer/evidence validation tests |
| Duplicate policy is visible | Exact/conflicting duplicate counts and stable validation issues |
| Combined rows are decomposed safely | NQ/FEVER/HotpotQA/MuSiQue contract tests |
| Missing corpus is not hidden | FEVER cannot become retrieval-ready without matching wiki source |
| Empty samples are not accepted | RGB/CRAG/Open RAG zero-row regression tests |
| CI remains small and offline | 25–100-query licensed or synthetic fixtures; no full downloads |
| Phase 2 work is absent | Import/tree tests forbid ingestion, indexing, embedding, and chunking additions |

## 10. Required Quality Gates

```bash
uv sync --frozen --extra dev
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest tests/unit tests/golden
uv run pytest -m integration
uv run python scripts/check_repository.py
docker compose config --quiet
```

Phase 1 may add adapter-specific contract commands, but none may require downloading full datasets
in CI.

## 11. Phase 1 Exit Gate

Phase 1 is complete only when:

- [ ] `/data/` is ignored and representative local files are proven ignored.
- [ ] Prepared source manifests use exact checksums and safe relative paths.
- [ ] The adapter protocol exposes four separate canonical streams.
- [ ] Dataset/split/source/adapter identities are explicit and versioned.
- [ ] One shared `SplitRole` drives protected-split policy.
- [ ] Validation reports empty values, duplicates, conflicting IDs, orphan references, and counts.
- [ ] BEIR compact collections pass source-specific contract and smoke tests.
- [ ] Natural Questions combined rows are decomposed with stable locators.
- [ ] FEVER visibly blocks retrieval readiness when its corpus is absent.
- [ ] RGB no longer reports a false successful zero-row sample.
- [ ] Completed Wave 2/3 adapters meet the same framework contract, or are explicitly retained as
      gated follow-up increments rather than advertised as working.
- [ ] Smoke fixtures are licensed for redistribution or synthetic and schema-equivalent.
- [ ] Repeated adapter execution is byte-deterministic.
- [ ] CI performs no full-data downloads and commits no raw/generated data.
- [ ] No ingestion, indexing, retrieval, generation, evaluation-runner, worker, PDF parser, or
      dynamic-provider implementation has been introduced.

## 12. Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Analysis heuristics misclassify fields | Review official schema per adapter and lock explicit mapping in golden tests. |
| Sample cap hides full-data behavior | Record sampling provenance and validate full manifests locally before claiming readiness. |
| Same dataset has multiple source variants | Include upstream revision, configuration, split role, and adapter version in identity. |
| Combined QA rows blur corpus and benchmark assets | Emit independent streams with shared provenance and typed join keys. |
| Missing FEVER wiki data produces misleading success | Separate answer-ready and retrieval-ready flags; missing corpus is a hard retrieval blocker. |
| Zero-byte/zero-row samples pass because the loader did not error | Require non-zero mandatory streams and explicit minimum-count validation. |
| Duplicate text is removed too early | Report source duplicates in Phase 1; perform content deduplication only in Phase 2. |
| Benchmark data or licenses leak into Git | Ignore `/data/`; review fixture licenses or use synthetic fixtures. |
| Later-phase logic grows inside adapters | Enforce import boundaries and keep parsing/chunking/indexing/query execution out of Phase 1. |

## 13. Handoff to Phase 2

Phase 2 receives immutable source manifests and validated corpus streams. It persists exact raw
bytes, parses documents into canonical trees, assigns hierarchy and locators, chunks only after
structure exists, and builds immutable indexes. Phase 2 must not consume benchmark queries,
judgments, or expected answers as ingestion documents.

The analysis capacity estimates remain planning inputs only. Phase 2 must repeat length and index
sizing with the selected tokenizer, complete source snapshot, embedding dimensions, OpenSearch
mapping, ANN settings, replicas, stored fields, and filesystem overhead.
