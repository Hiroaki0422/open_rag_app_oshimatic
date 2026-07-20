# Data Analysis Summary and Project Impact

**Status:** Informational input to Phase 1  
**Analysis date reviewed:** 2026-07-20  
**Related plan:** [Phase 1 Implementation Plan](./PHASE_1_IMPLEMENTATION_PLAN.md)

## Executive Summary

The collected data is useful enough to begin building the dataset-adapter framework, but it is
not uniform enough to feed directly into a RAG system.

The analysis successfully inspected 1,095 files and 191,522 sampled rows from a source archive
of about 1.1 GB. This gives us strong evidence about the range of formats, schemas, text lengths,
and quality problems the application must handle. It also shows that different benchmarks need
different rules. There is no safe, universal mapping from an arbitrary file to a document,
question, answer, or relevance judgment.

In practical terms, the project should start with a small, well-structured benchmark family,
prove the common adapter and validation framework, and then add harder datasets one at a time.
The BEIR compact collections are the best starting point. Datasets with missing corpora, empty
samples, nested records, PDFs, or dynamic web dependencies must remain gated until their source
and schema problems are resolved.

## What Was Analyzed

The local `data/analysis_outputs/` directory contains nine analysis artifacts covering:

- File inventory and load results
- Candidate mappings from source fields to documents, queries, judgments, and answers
- Field types and missing-value rates
- Identifier and duplicate profiles
- Text-length estimates
- Dataset readiness assessments
- Rough chunk and vector-storage estimates

The analysis was generated from `rag_dataset_subsets.zip`, whose recorded identity is:

- Size: 1,110,728,623 bytes
- SHA-256: `aaa0a4aead175da0a63d0039cd9866245124ef81ada102588151c73735dd1b2a`
- Archive members: 1,147
- Files analyzed: 1,095
- Files successfully loaded: 1,095
- Rows analyzed: 191,522

The analysis examined at most 5,000 rows per file. Its counts describe the sampled collection,
not necessarily the complete upstream datasets. The original archive and extracted records are
not currently present under `data/raw/`; only the analysis results are available locally.

## What We Learned

### The data is heterogeneous by design

Some benchmarks provide separate document, query, and relevance files. Others put the question,
answer, context, and evidence in one nested record. Still others depend on PDFs, Wikipedia, web
search, or knowledge graphs.

This means the application needs a dataset adapter for each benchmark family. A generic loader
can read JSON, JSONL, CSV, and TSV, but it cannot safely decide what a field means. Those meanings
must be reviewed and encoded explicitly.

### Automatic field guessing is not reliable enough

The analysis could not confidently classify 1,020 files. This does not mean those files are all
bad. Many are repository metadata, cached files, PDF-related assets, or formats whose field names
do not clearly reveal their purpose. It does mean that inferred mappings are suitable for
exploration only.

The project must use documented mappings for every supported dataset. An adapter should fail
with a clear explanation when a schema changes instead of quietly guessing.

### Missing and inconsistent values are common

The analysis found:

- 504 field-and-file combinations containing mixed value types
- 606 field-and-file combinations with less than 95% completeness
- 36 files where more than 5% of sampled records were exact duplicates

These issues require visible validation reports. Missing data may be valid in one benchmark and
a blocker in another, so the policy must be defined per dataset. Duplicate source records should
be reported and preserved during adaptation; destructive deduplication belongs in a later data
processing phase.

### Many documents will need structure-aware chunking

Fourteen document fields had a 95th-percentile length above an estimated 512 tokens. HotpotQA
contexts, for example, were around 2,023 estimated tokens at the 95th percentile.

Long documents are expected and should not be truncated by the dataset adapters. The adapters
must preserve the complete text and its source location. Phase 2 can then parse and chunk it while
maintaining evidence links.

The token figures are rough estimates based on character counts, not measurements from the final
tokenizer. They are useful for planning, but model-specific sizing must be repeated later.

### The estimated index size is manageable, but incomplete

At a nominal 512-token chunk size, the analyzed groups were estimated to produce roughly 230,889
chunks. The corresponding raw vector estimates suggest that local experimentation is practical.

This is not a production capacity forecast. It excludes full-dataset growth, text and metadata
storage, sparse indexes, approximate-nearest-neighbor structures, replicas, and filesystem
overhead. Phase 2 must run a real indexing pilot before infrastructure is sized.

## Readiness by Dataset Family

| Dataset family | What the analysis showed | Project decision |
| --- | --- | --- |
| BEIR compact collections | Separate corpus, query, and relevance files with generally clear IDs and text | Start here. Build SciFact first, then FiQA, NFCorpus, ArguAna, and TREC-COVID. |
| Natural Questions | Rich nested records containing questions, documents, annotations, and answer spans | Add after the framework is proven. Split each combined record into separate project concepts while preserving answer locations. |
| FEVER | Claims and evidence references are present, but the safe collection omitted the matching Wikipedia corpus | It can support claim/answer work, but must not be called retrieval-ready until the exact corpus is available. |
| RGB | Eight sampled files produced no rows | Treat this as a collection or sampling problem. Repair and review the source before implementing an adapter. |
| HotpotQA | Questions, answers, contexts, and supporting facts are present; contexts are relatively long | Good second-wave candidate. Preserve supporting-sentence references and defer chunking. |
| MuSiQue | Multi-hop records and answer aliases are present across several splits | Add in the second wave after explicitly separating benchmark data from repository metadata. |
| MultiHop-RAG | Separate corpus and benchmark records are available | Add in the second wave after confirming schemas and cross-file joins. |
| RAGBench | Multiple domain configurations are mixed with repository content | Inventory the official data files before treating it as one supported dataset. |
| Open RAG Benchmark | Many PDF-derived files and empty portable samples | Defer full support. Start with an inventory; PDF, table, and image handling belong in later phases. |
| CRAG | The portable task sample was empty and the benchmark relies on web or knowledge-graph behavior | Repair the sample first. Future retrieval will require provider integrations rather than only a static local index. |

## How This Changes the Project

### Phase 1 becomes a normalization and trust layer

Phase 1 should not index documents or run RAG queries. Its job is to turn supported source data
into four clear streams:

- Documents that may later be indexed
- Benchmark questions
- Relevance or evidence judgments
- Expected answers or labels

Keeping these separate prevents answers and test evidence from accidentally entering the search
corpus. It also lets retrieval quality and answer quality be measured independently later.

### Dataset identity and provenance must be explicit

Every prepared dataset needs a manifest containing its exact source version, checksums, files,
sampling method, and split roles. File paths and directory names alone are not reliable dataset
identifiers.

This is essential for reproducibility. If an upstream alias or file changes, the project must be
able to tell that it is no longer using the same dataset snapshot.

### Test-split protection must be based on metadata

The collection contains many split names and conventions. A name such as `challenge`,
`blind_test`, or `paper_test` cannot safely determine how the split may be used.

Each adapter must explicitly label a split as training, development, or test data. Development
and tuning workflows must reject test-role data regardless of its filename. This preserves honest
final evaluation results.

### Validation must fail visibly

A file loading without an exception is not enough. An adapter is not ready when it emits zero
required records, loses IDs, has conflicting duplicate IDs, references missing documents, or
cannot find its required corpus.

Validation should produce a readable and machine-readable report explaining which use cases are
safe. For example, FEVER may be ready for answer evaluation while still being unready for
retrieval evaluation.

### CI should use small, reviewed fixtures

The full datasets and generated analysis outputs should remain outside Git. Continuous
integration should use small licensed or synthetic fixtures that reproduce the official schemas
and important failure cases. Full snapshots can be validated locally by checksum without being
committed.

## What the Analysis Does Not Prove

The current analysis does not prove that:

- Every upstream dataset was collected completely
- Inferred field mappings match the official schemas
- The sampled row counts represent full-dataset sizes
- Approximate token counts match the tokenizer selected later
- Estimated raw vector size equals an OpenSearch deployment's disk or memory needs
- A dataset is retrieval-ready merely because its files loaded successfully
- Empty RGB, CRAG, or Open RAG samples represent genuinely empty upstream datasets

These limits should be carried into design reviews and status reporting so exploratory results
are not presented as production guarantees.

## Recommended Path Forward

1. Restore the source archive and verify it against the recorded checksum.
2. Build the shared manifest, reader, adapter, and validation contracts.
3. Prove the full path with SciFact and then the remaining compact BEIR collections.
4. Add Natural Questions and FEVER with explicit readiness rules.
5. Repair the RGB sample before claiming support.
6. Add the well-formed multi-hop datasets in a second wave.
7. Keep PDF-heavy, repository-heavy, empty, and dynamic-source datasets behind readiness gates.
8. Repeat tokenizer and index sizing with complete data during Phase 2.

The most important outcome of the analysis is not a single size estimate. It is the evidence that
data quality, schema meaning, and provenance must be enforced as first-class parts of the system.
That foundation will make later retrieval and evaluation results reproducible and believable.
