# Proposal: Module Context Retrieval — Fase 2

## Intent

Fase 1 sends only the transcript to Groq, so generated descriptions stay generic: the model cannot name the affected Kawak module or reflect its documented behavior, and the analyst still supplies that context by hand. Fase 2 injects curated module context from `memory/` between transcription and generation — grounded in real docs, still inventing nothing.

## Scope

### In Scope
- New retrieval module (never imports `streamlit`): reads `MEMORY.md` + `modulos/*`, scores modules, returns bounded context or nothing.
- `MEMORY_DIR` env var — path configurable, read-only, never written.
- Fixture `memory/` at repo root (`MEMORY.md`, 2–3 `modulos/<n>/_modulo.md`, `core/`, `errores_comunes.md`, `decisiones_tecnicas.md`) for dev/test only.
- `generar_descripcion.py`: optional `contexto` parameter, new delimited context block, strengthened anti-invention rules.
- `app.py`: retrieval call between transcribe and generate; typed error mapped to `st.error`.
- Unit tests; `.env.example`, README, `CLAUDE.md` updates.

### Out of Scope
- Embeddings / Chroma / vector index / reindex pipeline (Fase 5; revisit only if lexical matching demonstrably misses).
- Fase 3 ticket-format prompt tuning, Fase 4 Docker/nginx, Fase 5 history & model tuning.
- Wiring the real external Kawak `memory/` — deploy-time `MEMORY_DIR` config, not code.

## Capabilities

### New Capabilities
- `context-retrieval`: locate `memory/`, score modules against the transcript, return bounded context or none, never write.

### Modified Capabilities
- `jira-description-generation`: supersede **Transcript-Only Submission** — the Groq call MUST include retrieved module context when a module clears the threshold, MUST stay transcript-only otherwise, and grounding MUST NOT weaken the anti-invention rules.

## Approach

Exploration Approach 3 (index-assisted lexical matching). Score each module by fuzzy match on folder name/aliases **plus** normalized token overlap with its `MEMORY.md` prose description (Spanish accent/case normalization, stopword filtering). Top-N above threshold → concatenate `_modulo.md` content under a character budget into a new delimited prompt block. Nothing above threshold → omit the block entirely (Fase 1 behavior). Pure I/O and string operations: no ML runtime, deterministic, explainable in tests.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `contexto_memoria.py` (name TBD) | New | Whole retrieval lifecycle + typed error |
| `memory/` | New | Dev/test fixture; production overrides via `MEMORY_DIR` |
| `generar_descripcion.py` | Modified | `contexto` param, context block, new grounding rules |
| `app.py` | Modified | Retrieval between transcribe and generate; error mapping |
| `tests/test_contexto_memoria.py` | New | Scoring, no-match, budget, read-only |
| `requirements.txt`, `.env.example`, docs | Modified | Optional `rapidfuzz`; `MEMORY_DIR` |
| `openspec/specs/jira-description-generation/spec.md` | Modified | Delta in spec phase |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Real `MEMORY.md` descriptions too terse → matching degrades to folder names | High | Document the expected format as a cross-team contract; fixture mirrors it |
| Wrong module injected (ambiguous transcript) | Med | Confidence threshold + top-N policy set in design; no-match omits context |
| Model invents detail about the retrieved module | Med | New explicit rule: only literal content of the injected block |
| Prompt exceeds Groq input window | Med | Character/token budget + truncation; confirm window at design time |
| Accidental write to a read-only mount | Low | Read-only-only API surface plus a test asserting no writes |

## Rollback Plan

Additive module + fixture, plus two small edits. Revert the single PR. Softer rollback without a deploy: unset `MEMORY_DIR` or point it at a missing folder — retrieval returns no context and the app degrades exactly to Fase 1. No data, no migration, no schema.

## Dependencies

- Format contract with the external team owning the real Kawak `memory/` (fixture is a proxy, unverified).
- Optional `rapidfuzz`; `GROQ_API_KEY` still blocks end-to-end verification.
- Groq context-window figure for `llama-3.3-70b-versatile` (confirm in design).

## Success Criteria

- [ ] Transcript naming a fixture module in plain language (e.g. "el módulo donde se ven los riesgos") retrieves that module's context.
- [ ] Unmatched transcript produces byte-identical Fase 1 behavior (no context block).
- [ ] Generated text uses only transcript + injected context; no invented module detail.
- [ ] `MEMORY_DIR` selects the folder; missing/unreadable path degrades gracefully, never crashes.
- [ ] Retrieval module unit-testable without Streamlit and provably never writes to `memory/`.
