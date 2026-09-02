# Delta for Context Retrieval

> This delta is written against the REAL current implementation
> (`contexto_memoria.py`, schema-free, Groq-assisted selection), not
> against the STALE fixed-schema text in `openspec/specs/context-retrieval/spec.md`.
> The REMOVED requirements below describe that stale, no-longer-true
> design; the ADDED requirements describe accurate current behavior plus
> this change's enrichment integration. Unlisted requirements ("Bounded
> Context Size", "Configurable, Read-Only Memory Location", "Graceful
> Degradation on Missing/Unreadable Memory", "Retrieval Invisible to
> Analyst", "Standalone Testable Module") remain accurate and unchanged.

## REMOVED Requirements

### Requirement: Module Scoring Against Transcript

(Reason: superseded by schema-free, Groq-assisted document selection — the real `MEMORY_DIR` corpus has no `MEMORY.md`/`modulos/` layout to score against; see `CLAUDE.md` "Context retrieval decision".)
(Migration: replaced by "Schema-Free Discovery and Groq-Assisted Selection" below.)

### Requirement: Top-N Threshold-Based Injection

(Reason: there is no per-module numeric score to threshold against under the schema-free design; Groq itself judges relevance from a file listing instead of a lexical score.)
(Migration: replaced by "Schema-Free Discovery and Groq-Assisted Selection" below.)

### Requirement: Module Context Scope Restricted to `_modulo.md`

(Reason: there is no `_modulo.md`/module-folder convention in the real documentation corpus; any `.md` file anywhere under `MEMORY_DIR` is a candidate.)
(Migration: replaced by "Schema-Free Discovery and Groq-Assisted Selection" and "Enriched-or-Raw Context Block Assembly" below.)

## ADDED Requirements

### Requirement: Schema-Free Discovery and Groq-Assisted Selection

The system MUST discover every `.md` file anywhere under `MEMORY_DIR`, regardless of folder layout, and MUST NOT require any fixed index file or per-module naming convention. The system MUST send a lightweight preview listing of candidate documents to Groq and MUST select only paths Groq returned that were actually present in that listing, capped at a fixed maximum count.

#### Scenario: Flat or nested corpus discovered without a fixed schema
- GIVEN `MEMORY_DIR` contains `.md` files in an arbitrary folder layout with no index file
- WHEN discovery runs
- THEN every `.md` file MUST be found as a candidate regardless of its folder depth or naming convention

#### Scenario: Model never invents a path
- GIVEN Groq's selection response names a path not present in the listing
- WHEN the system reads that response
- THEN the invented path MUST be discarded and MUST NOT appear in the final selection

### Requirement: Enriched-or-Raw Context Block Assembly

When assembling context for the final-selected documents, the system MUST use each document's enriched functional summary when one is available and MUST fall back to that document's verbatim raw content otherwise. The system MUST preserve selection order when building blocks and MUST still enforce the existing character budget and deterministic truncation across the assembled blocks.

#### Scenario: Enriched summary available
- GIVEN a selected document has a valid enriched summary
- WHEN the context block for that document is assembled
- THEN the block MUST contain the enriched summary, not the raw file content

#### Scenario: Enrichment unavailable for a document
- GIVEN a selected document's enrichment failed or was never produced
- WHEN the context block for that document is assembled
- THEN the block MUST contain that document's verbatim raw content

#### Scenario: Budget still enforced over enriched blocks
- GIVEN the concatenated enriched-or-raw blocks of the selected documents exceed the configured character budget
- WHEN context is assembled
- THEN the system MUST truncate deterministically to fit within budget, exactly as it does today for raw blocks
