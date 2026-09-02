# Archive Report: enriquecimiento-documentacion-haiku

## Summary

Added a Claude Haiku 4.5-based enrichment layer over the context-retrieval
pipeline: each finally-selected `.md` document is turned into a short,
plain-language functional summary (senior-developer-style), cached by
SHA-256 of the raw content under `cache/documentacion/`, so the cost is
paid once per unique document, never per query. Falls back to the raw
document content on any failure (missing key, API error, cache write
failure) — the retrieval pipeline never blocks or breaks.

## Outcome

- **Status**: PASS WITH WARNINGS, 0 CRITICAL (verify-report.md).
- **Tests**: 99/99 passing (1 pre-existing unrelated skip), including a
  concurrency test that genuinely forces out-of-submission-order
  completion and asserts result order is still preserved.
- **New module**: `contexto_enriquecido.py` — Anthropic client
  (`claude-haiku-4-5-20251001`), atomic tmp+`Path.replace()` cache writes,
  a separate 429-retry wrapper (Anthropic's call/error shape differs from
  Groq's, confirmed live against `anthropic` SDK v1.3.0), and
  `ThreadPoolExecutor`-based concurrent enrichment for cache misses only,
  preserving original selection order.
- **Integration**: `contexto_memoria.py::buscar_contexto()` gained one
  new call site (raw `read_text()` loop → `(ruta, contenido)` pairs →
  `enriquecer_documentos()`), with defense-in-depth: any enricher failure
  or length mismatch degrades to the raw blocks, never to `""`.
- **No changes** to `generar_descripcion.py` or `consultar_documentacion.py`
  — confirmed via `git diff` during verify.

## Specs merged

- **ADDED** `openspec/specs/documentation-enrichment/spec.md` (new domain).
- **MODIFIED** `openspec/specs/context-retrieval/spec.md` — this also
  resolved the long-standing **STALE** banner left on that file since the
  schema-free retrieval redesign was implemented outside the SDD cycle:
  removed 3 requirements describing the old fixed-schema/lexical-scoring
  design (`Module Scoring Against Transcript`, its threshold rule, and the
  `_modulo.md`-only scope restriction) and added 2 requirements describing
  the real current behavior (`Schema-Free Discovery and Groq-Assisted
  Selection`, `Enriched-or-Raw Context Block Assembly`). Five other
  requirements (`Bounded Context Size`, `Configurable, Read-Only Memory
  Location`, `Graceful Degradation`, `Retrieval Invisible to Analyst`,
  `Standalone Testable Module`) were verified still accurate and left
  untouched.

## Outstanding manual follow-ups (operator-owned, not blockers)

1. **`.env.example`**: add `ANTHROPIC_API_KEY=` (blocked by the same
   permission guardrail that has blocked every prior phase's `.env*`
   edits — confirmed again this change).
2. **Manual smoke — real key**: confirm the cache populates on first use
   and a repeat query for the same document makes zero Haiku calls.
3. **Manual smoke — Docker persistence**: confirm `cache/documentacion/`
   survives a `docker compose down && up` (volume-mounted, not baked into
   the image).
4. The fourth originally-listed manual task (unset-key behavior) is
   already covered by an automated unit test — no manual action needed.

## Traceability (Engram observation IDs)

- Explore: `sdd/enriquecimiento-documentacion-haiku/explore`
- Proposal: id 162
- Spec: id 163
- Design: id 164
- Tasks: id 165
- Apply-progress: id 166
- Verify-report: id 167
