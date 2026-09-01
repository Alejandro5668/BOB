# Exploration: Fase 2 — Context retrieval (RAG) between transcript and Groq generation

## Current State

Fase 1 (archived at `openspec/changes/archive/2026-09-01-asistente-voz-fase1/`) established three root-level Python modules with one dependency direction: `app.py` (Streamlit) → `transcribir.py` (local Whisper) and `generar_descripcion.py` (Groq `llama-3.3-70b-versatile`). Neither domain module imports `streamlit` — this is exactly the seam Fase 2 needs.

`generar_descripcion.py` today owns `SYSTEM_PROMPT` (7 anti-invention rules) and `PLANTILLA_USUARIO` (single `{transcripcion}` slot, `---`-delimited). It sends only the transcript, per the Fase 1 spec's "Transcript-Only Submission" requirement, which Fase 2 will need to supersede in the spec phase.

Fase 1's own `proposal.md` already flags the exact question posed here — a "Note for Fase 2" section suggesting folder-name keyword matching as a simplification over the PDF's `sentence-transformers` + `Chroma` plan, explicitly deferring the decision to this exploration.

Confirmed: `memory/` does not exist anywhere in the repo. `openspec/changes/asistente-voz-fase2/state.yaml` shows all phases pending, hybrid artifact store, single-pr delivery. The PDF's own phase split places "reindex, model tuning" in **Fase 5**, not Fase 2 — relevant scope evidence against building a vector-index pipeline now.

## Affected Areas
- `generar_descripcion.py` — needs an optional `contexto` param, extended `PLANTILLA_USUARIO`, strengthened `SYSTEM_PROMPT` grounding rules
- `app.py` — must call retrieval between transcribe and generate, map a new typed retrieval error like the existing four
- New retrieval module (name TBD in design) — must not import `streamlit`, independently testable like the other two modules
- New fixture `memory/` at repo root — `MEMORY.md`, `modulos/<nombre>/_modulo.md` (2-3 examples), `core/*.md`, `errores_comunes.md`, `decisiones_tecnicas.md`
- `requirements.txt`, `.env.example` — env var for external `memory/` path (e.g. `MEMORY_DIR`) documented for production
- `openspec/specs/jira-description-generation/spec.md` — "Transcript-Only Submission" requirement needs superseding (spec phase, not now)
- New `tests/test_contexto_memoria.py` mirroring the existing fake-client/fake-model test pattern

## Approaches

1. **Pure keyword/folder-name matching** — match transcript against `memory/modulos/<name>/` folder names directly.
   - Pros: zero new heavy deps, no reindex pipeline, deterministic/debuggable, matches Fase 1's own suggestion.
   - Cons: fails whenever the analyst doesn't say the literal technical name — the "el módulo donde se ven los riesgos" vs. `gsr_riesgos` gap is real, not hypothetical, given Fase 1's plain-language premise.
   - Effort: Low

2. **Embeddings (sentence-transformers + Chroma)** — index module docs, cosine-similarity search against the embedded transcript.
   - Pros: handles genuine zero-overlap paraphrase, scales to larger `memory/`.
   - Cons: adds heavy ML deps (torch, sentence-transformers, chromadb) to a project with none today; needs a Spanish-capable model decision; needs a reindex/staleness subsystem for an externally-owned, read-only-mounted folder — duplicating work the PDF plan already scopes for Fase 5; harder to unit-test deterministically; slower cold start alongside Whisper.
   - Effort: High

3. **Hybrid: index-assisted lexical matching (recommended)** — score each module by folder-name/alias match AND keyword overlap against `MEMORY.md`'s natural-language description of that module; take top-N above threshold, inject bounded content; no match → omit context block (graceful degradation).
   - Pros: because `MEMORY.md` is human-curated prose, matching its descriptions closes much of the paraphrase gap for free (a risk-module description likely contains the word "riesgos" even if the folder name doesn't lexically match the phrase spoken); no heavy deps, no vector DB, no reindex pipeline; explainable and unit-testable.
   - Cons: still lexical at its core — a true zero-overlap paraphrase would still miss; requires documenting an expected `MEMORY.md`/`_modulo.md` format as a de facto contract with the external team that owns the real folder.
   - Effort: Medium (closer to Low than to embeddings)

## Recommendation

Approach 3. The concrete failure case — analyst not saying the technical name — is very likely still caught by matching against `MEMORY.md`'s descriptive text rather than the bare folder name. Given fixture/realistic `memory/` size, lexical scoring over module descriptions is cheap, deterministic, and avoids front-loading the reindex/staleness subsystem the phase plan already schedules for Fase 5. Treat embeddings as a fallback to revisit only if real usage shows lexical matching missing matches in practice — don't build it speculatively now.

## Risks
- Fixture-vs-real `memory/` divergence: the real external `MEMORY.md`'s description quality is unverified; terse entries would shrink the lexical approach's advantage.
- Ambiguous/multi-module references: no mid-flow disambiguation possible in a single non-interactive generation call.
- No-match handling: must degrade to Fase 1 behavior, never force a wrong best-effort guess.
- Prompt size limits: need a token/character budget and truncation policy; Groq's actual context window for the current model needs confirming at design time, not assumed.
- Stronger anti-invention under grounding: existing 7-rule `SYSTEM_PROMPT` needs new rules so the model doesn't invent details even about the retrieved module.
- Read-only mount discipline: retrieval module must never attempt to write to `memory/`.
- Spanish text normalization (accents/casing) needed before matching to avoid false negatives.

## Ready for Proposal

Yes.
