# Documentation Enrichment Specification

## Purpose

Converts each final-selected raw Markdown document into a concise, non-technical functional summary via Claude Haiku before it is assembled into the Groq prompt, caching results by content hash so a repeat request over an unchanged document incurs no LLM cost. Enrichment degrades to verbatim raw content on any failure and never touches the lightweight preview-listing stage.

## Requirements

### Requirement: Content-Addressed Enrichment Cache

The system MUST derive a SHA-256 hash of each document's raw content and MUST use that hash as the cache key when reading or writing an enrichment result. The system MUST invalidate a cache entry only when the hashed content changes; it MUST NOT invalidate based on prompt text or model version.

#### Scenario: Repeat request over unchanged document
- GIVEN a document was previously enriched and cached
- WHEN the same document (byte-identical content) is selected again
- THEN the system MUST read the cached summary and MUST NOT call the Haiku API for that document

#### Scenario: Document content changes
- GIVEN a document's raw content changed since it was last cached
- WHEN that document is selected
- THEN the system MUST compute a new hash, treat it as a cache miss, and produce a fresh enrichment

### Requirement: Haiku Summarization With Mandatory Raw Fallback

The system MUST summarize a selected document's functional behavior (not implementation detail) via the Haiku model on a cache miss. The system MUST fall back to that document's verbatim raw content, and MUST NOT raise or abort the overall request, when `ANTHROPIC_API_KEY` is missing, the API call fails, or the cache write fails.

#### Scenario: Successful enrichment
- GIVEN a document is a cache miss and the API key is configured
- WHEN enrichment runs
- THEN the returned block MUST be the Haiku-produced functional summary, and it MUST be cached for future reuse

#### Scenario: Missing API key
- GIVEN `ANTHROPIC_API_KEY` is unset
- WHEN enrichment is attempted for any document
- THEN the system MUST return that document's raw content unmodified and MUST NOT raise

#### Scenario: API error for one document among several
- GIVEN two or more documents are selected and the Haiku call fails for only one of them
- WHEN enrichment completes
- THEN only the failing document's block MUST fall back to raw content; the other documents' blocks MUST remain enriched

### Requirement: Bounded Concurrent Enrichment Preserving Order

WHEN two or more selected documents are cache misses simultaneously, the system MUST enrich them concurrently under a bounded worker pool and MUST return resulting blocks in the same order as the original document selection, regardless of completion order.

#### Scenario: Multiple concurrent cache misses
- GIVEN three selected documents are all cache misses
- WHEN enrichment runs
- THEN the system MUST submit them to a bounded concurrent pool and MUST return their blocks in original selection order even if a later document's API call completes first

### Requirement: Enrichment Scope Restricted to Final Selection

The system MUST apply enrichment only to documents already chosen by the final document-selection step. The system MUST NOT enrich documents during the lightweight preview-listing stage used to choose relevant documents.

#### Scenario: Preview listing stays unenriched
- GIVEN the system is building the preview listing to ask Groq which documents are relevant
- WHEN that listing is constructed
- THEN no document's content MUST be sent to Haiku at that stage
