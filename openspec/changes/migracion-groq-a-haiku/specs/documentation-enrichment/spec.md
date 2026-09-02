# Delta for Documentation Enrichment

This domain is retired in full — replaced by `context-retrieval`'s raw
full-document injection. All requirements below are removed.

## REMOVED Requirements

### Requirement: Content-Addressed Enrichment Cache

(Reason: Claude Haiku 4.5 is now both the document selector and the final reader of full raw content; caching a lossy compressed summary of the same source it reads directly adds cost and complexity without benefit, and costs completeness.)
(Migration: Superseded by `context-retrieval`'s "Raw Full-Document Context Block Assembly" requirement. The `cache/documentacion/` cache directory is deleted; no functional replacement is needed.)

### Requirement: Haiku Summarization With Mandatory Raw Fallback

(Reason: Raw injection removes the need for a summarization pass entirely.)
(Migration: `contexto_enriquecido.py` is renamed to `cliente_anthropic.py` and slimmed to shared client/retry scaffolding (`_crear_cliente`, `_crear_mensaje_con_reintento`, `ErrorConfiguracion`) reused by selection, generation, and verification. No summarization replacement is needed.)

### Requirement: Bounded Concurrent Enrichment Preserving Order

(Reason: With enrichment removed there is no per-document LLM call left to parallelize at this stage; raw content is read directly from disk.)
(Migration: None — selection-order preservation is retained by `context-retrieval`'s raw assembly requirement, which needs no concurrency.)

### Requirement: Enrichment Scope Restricted to Final Selection

(Reason: The distinction between the preview-listing stage and an enrichment stage no longer applies once enrichment itself is removed.)
(Migration: None.)
