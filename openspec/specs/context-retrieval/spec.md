# Context Retrieval Specification

## Purpose

Locates and scores Kawak modules documented under `memory/` against the approved transcript, and returns bounded, literal context for the top matching module(s) — or nothing when no module clears the confidence threshold. Retrieval is invisible to the analyst during normal operation and degrades gracefully when `memory/` is absent or unreadable.

## Requirements

### Requirement: Schema-Free Discovery and Haiku-Assisted Selection

The system MUST discover every `.md` file anywhere under `MEMORY_DIR`, regardless of folder layout, and MUST NOT require any fixed index file or per-module naming convention. The system MUST send a lightweight preview listing of candidate documents to Claude Haiku 4.5 and MUST select only paths Haiku returned that were actually present in that listing, capped at a fixed maximum count.

#### Scenario: Flat or nested corpus discovered without a fixed schema
- GIVEN `MEMORY_DIR` contains `.md` files in an arbitrary folder layout with no index file
- WHEN discovery runs
- THEN every `.md` file MUST be found as a candidate regardless of its folder depth or naming convention

#### Scenario: Model never invents a path
- GIVEN Haiku's selection response names a path not present in the listing
- WHEN the system reads that response
- THEN the invented path MUST be discarded and MUST NOT appear in the final selection

### Requirement: Raw Full-Document Context Block Assembly

When assembling context for the final-selected documents, the system MUST use each document's verbatim raw content. No enriched or summarized intermediate form MUST be produced, consulted, or fallen back to at this stage. The system MUST preserve selection order when building blocks.

#### Scenario: Selected document injected as raw content
- GIVEN a document was selected by Haiku
- WHEN the context block for that document is assembled
- THEN the block MUST contain that document's verbatim raw content, not a summary

#### Scenario: Selection order preserved across blocks
- GIVEN two or more documents were selected
- WHEN blocks are assembled
- THEN blocks MUST appear in the same order as the original selection

### Requirement: Bounded Context Size

The system MUST enforce a 120,000-character budget (~30K tokens) across all injected raw document blocks and MUST truncate deterministically rather than exceed it.

#### Scenario: Combined raw content exceeds budget
- GIVEN the concatenated raw content of the selected documents exceeds 120,000 characters
- WHEN context is assembled
- THEN the system MUST truncate deterministically to fit within the 120,000-character budget

#### Scenario: Combined raw content within budget
- GIVEN the concatenated raw content is within 120,000 characters
- WHEN context is assembled
- THEN the content MUST be included unmodified

### Requirement: Configurable, Read-Only Memory Location

The system MUST resolve the memory root from the `MEMORY_DIR` environment variable and MUST NOT write to it under any code path.

#### Scenario: MEMORY_DIR points to a valid folder
- GIVEN `MEMORY_DIR` is set to a readable folder containing `MEMORY.md` and `modulos/`
- WHEN retrieval runs
- THEN the system MUST read from that folder

#### Scenario: Retrieval never writes to memory
- GIVEN retrieval runs against a fixture folder
- WHEN a test inspects filesystem calls
- THEN no write, create, or delete operation MUST have occurred against `MEMORY_DIR`

### Requirement: Graceful Degradation on Missing/Unreadable Memory

WHEN `MEMORY_DIR` is unset, missing, or unreadable, the system MUST degrade to Fase 1 behavior (no context injected) and MUST surface a non-blocking notice to the analyst. It MUST NOT raise a hard error or crash, and MUST NOT fail silently.

#### Scenario: MEMORY_DIR unset or path missing
- GIVEN `MEMORY_DIR` is unset or points to a non-existent path
- WHEN the analyst requests generation
- THEN the system MUST proceed with transcript-only submission and MUST display a non-blocking notice that context was unavailable

#### Scenario: MEMORY_DIR set but unreadable
- GIVEN `MEMORY_DIR` points to a folder the process cannot read
- WHEN the analyst requests generation
- THEN the system MUST proceed with transcript-only submission and MUST display a non-blocking notice that context was unavailable

### Requirement: Retrieval Invisible to Analyst

The system MUST NOT expose which module(s) matched, scores, or any retrieval indicator in the UI during normal operation. The only user-visible retrieval-related signal MUST be the degrade notice defined above.

#### Scenario: Successful match produces no UI indicator
- GIVEN retrieval matched one or more modules above threshold
- WHEN the analyst views the screen before and after generation
- THEN no indicator of which module(s) matched or their scores MUST appear anywhere in the UI

#### Scenario: Degrade notice is the only visible retrieval-related signal
- GIVEN retrieval degraded due to missing/unreadable `MEMORY_DIR`
- WHEN the analyst views the screen
- THEN the only retrieval-related UI element MUST be the non-blocking degrade notice

### Requirement: Standalone Testable Module

The retrieval module MUST be importable and testable without a running Streamlit session and MUST NOT import `streamlit`.

#### Scenario: Unit test invokes retrieval directly
- GIVEN a test imports the retrieval module and points `MEMORY_DIR` at a fixture folder
- WHEN it calls the scoring/retrieval function with a sample transcript
- THEN the system MUST return scored/matched results without any Streamlit dependency
