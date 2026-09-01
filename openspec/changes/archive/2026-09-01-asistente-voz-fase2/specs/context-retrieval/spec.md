# Context Retrieval Specification

## Purpose

Locates and scores Kawak modules documented under `memory/` against the approved transcript, and returns bounded, literal context for the top matching module(s) — or nothing when no module clears the confidence threshold. Retrieval is invisible to the analyst during normal operation and degrades gracefully when `memory/` is absent or unreadable.

## Requirements

### Requirement: Module Scoring Against Transcript

The system MUST score each module under `MEMORY_DIR/modulos/*` against the transcript by combining fuzzy matching on the module's folder name/aliases with normalized token overlap against that module's `MEMORY.md` prose description (case/accent-insensitive, stopword-filtered).

#### Scenario: Transcript names a module in plain language
- GIVEN a transcript containing "el módulo donde se ven los riesgos"
- WHEN the system scores modules
- THEN the module documenting risk-related behavior MUST receive the highest score

#### Scenario: Transcript has no recognizable module reference
- GIVEN a transcript with no wording matching any module's name, aliases, or description
- WHEN the system scores modules
- THEN every module MUST score below the configured threshold

### Requirement: Top-N Threshold-Based Injection

The system MUST rank modules by score and inject the top-N modules whose score clears the configured threshold. When more than one module clears the threshold, all qualifying modules up to N MUST be injected together — this MUST NOT be treated as a no-match/ambiguous case.

#### Scenario: Single module clears threshold
- GIVEN exactly one module scores above threshold
- WHEN retrieval completes
- THEN only that module's context MUST be returned

#### Scenario: Multiple modules clear threshold
- GIVEN two or more modules score above threshold
- WHEN retrieval completes
- THEN the top-N qualifying modules MUST all be returned together as context

#### Scenario: No module clears threshold
- GIVEN every module scores below threshold
- WHEN retrieval completes
- THEN no context MUST be returned, and the subsequent Groq request MUST be byte-identical to Fase 1 behavior

### Requirement: Module Context Scope Restricted to `_modulo.md`

For each injected module, the system MUST include only that module's `_modulo.md` content. It MUST NOT include `core/`, `errores_comunes.md`, `decisiones_tecnicas.md`, or raw `MEMORY.md` content in the injected context.

#### Scenario: Matched module context includes only `_modulo.md`
- GIVEN a module cleared threshold
- WHEN its context is assembled
- THEN the assembled context MUST equal that module's `_modulo.md` content only

#### Scenario: Shared files never leak into injected context
- GIVEN retrieval ran successfully
- WHEN the injected context is inspected
- THEN it MUST NOT contain any content from `core/`, `errores_comunes.md`, `decisiones_tecnicas.md`, or `MEMORY.md`

### Requirement: Bounded Context Size

The system MUST enforce a character/token budget across all injected module context and MUST truncate deterministically rather than exceed it.

#### Scenario: Combined content exceeds budget
- GIVEN the concatenated `_modulo.md` content of the top-N modules exceeds the configured budget
- WHEN context is assembled
- THEN the system MUST truncate deterministically to fit within budget

#### Scenario: Combined content within budget
- GIVEN the concatenated content is within budget
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
