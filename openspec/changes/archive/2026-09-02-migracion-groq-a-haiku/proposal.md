# Proposal: Retire Groq, run all LLM processing on Claude Haiku 4.5

## Intent

Analyses are vague because selected documentation is compressed into 4–8 line summaries before reaching the generator. Groq (`gpt-oss-20b`/`120b`) also forces a second provider, a second key, and a second retry dialect. Move selection, anti-hallucination verification, generation and Q&A onto `claude-haiku-4-5-20251001` only, and inject full raw `.md` content instead of summaries — Haiku's 200K window makes compression unnecessary. Outcome: more complete grounded answers, one provider, fewer round trips.

## Scope

### In Scope
- Repoint all 4 Groq call sites (`_preguntar_selector`, `generar_descripcion`, `_verificar_resultado_esperado`, `responder_consulta`) to Haiku 4.5.
- Remove the enrichment step; `buscar_contexto()` injects verbatim raw content of selected docs.
- Slim + rename `contexto_enriquecido.py` → `cliente_anthropic.py` as the single shared client/retry/error toolkit.
- Delete dead code: `_crear_completion_con_reintento`, `ENRIQUECEDOR_*` prompts, enrichment cache, `groq` from `requirements.txt`.
- Rewrite `FakeGroq` fixtures as `FakeAnthropic` in 3 test files; re-scope `test_contexto_enriquecido.py`.
- **`qa-documentacion` (added mid-cycle, user request):** `responder_consulta()` returns a 3-state `RespuestaConsulta(texto, tipo)` instead of a bare `str` — plain analyst-facing answer, one clarifying question when the query is ambiguous/under-specified, or the existing `SIN_INFORMACION` degrade (now structurally distinct from "uncertain/varies by case"). `app.py` branches on `tipo` to render each state. New/rewritten prompt in `prompts.py` bans the reserved no-information sentence from any state other than `SIN_INFORMACION`.

### Out of Scope
- `transcribir.py` / ElevenLabs — untouched.
- Prompt caching (`cache_control`) — see decision 4.
- Sonnet/Opus routing, model-tier selection, streaming.
- Multi-turn clarification (the analyst re-submits after editing the transcription; no conversation history is kept).

## Capabilities

### New Capabilities
- `qa-documentacion`: plain-language Q&A answers, uncertainty/case-variability signaling, one clarifying question on ambiguous queries, full raw-context grounding shared with `context-retrieval` — 5 ADDED requirements, 8 scenarios. Added mid-cycle after the user flagged that Q&A deserved real behavior, not just a provider repoint.

### Modified Capabilities
- `context-retrieval`: selection provider becomes Haiku; "Enriched-or-Raw Block Assembly" becomes always-raw-full-content; budget value changes.
- `jira-description-generation`: "API Key Fail-Fast" moves from `GROQ_API_KEY` to `ANTHROPIC_API_KEY`; anti-hallucination requirement re-synced (already stale).
- `documentation-enrichment`: REMOVED requirements — the enrichment capability is retired (Reason + Migration required).

## Approach — resolved decisions

| # | Question | Decision | Why |
|---|---|---|---|
| 1 | Fatal vs non-fatal client error | One `ErrorConfiguracion` in `cliente_anthropic`; **fatality is a call-site policy**. Generation/Q&A let it propagate (fail-fast preserved); `buscar_contexto` and the verifier catch and degrade. | Two exception types for one condition is the actual defect; keeps both existing contracts without a duplicate class. |
| 2 | Raw-context budget | `PRESUPUESTO_CARACTERES = 120_000` (~30K tokens, 15% of the window). | Max 3 selected docs → ~40KB each before truncation, so real Kawak per-screen docs pass whole. Truncation stays as safety valve, not the normal path. Worst case ≈ $0.03 input/generation. |
| 3 | Client sharing | Build **one** client per top-level request, thread through selection → generation → verification; keep `cliente=None` lazy fallback. | One 429 budget, one test seam, no behavior change when omitted. |
| 4 | Prompt caching | **Dropped from scope**, deferred as `cache-contexto-consultas`. | Static prompt ≈1,000 tokens is below Haiku's ~4,096-token cache floor — it would silently never cache. The raw-context block would clear it, but no code path currently reuses one context set within a TTL, so it needs a session-scoped context identity first. Correcting the original suggestion, not dropping it silently. |
| 5 | Merge verifier into generation | **No** — verification stays a separate pass. | Self-grading the text you just wrote is a real reliability regression against a product guarantee; the verifier is conditional and cheap (150 tokens). Speed goal is met instead by deleting N enrichment calls per request. |
| 6 | `contexto_enriquecido.py` | Approach 2 confirmed, **rename included in this change**. | Only 3 importers; deferring leaves a misleading filename and a second PR over the same files. Its `FakeAnthropic` becomes the shared reference fake. |
| 7 | Dead-code cleanup | **In scope**, not a follow-up. | A `groq` entry no code imports is a false manifest; orphan prompt constants violate the repo's prompt-repository convention. All removals are mechanical and test-verifiable. |

Round trips per request drop from `selection + N enrichment + generation + (verifier)` to `selection + generation + (verifier)`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `contexto_enriquecido.py` → `cliente_anthropic.py` | Modified/Renamed | Slimmed to `_crear_cliente`, `_crear_mensaje_con_reintento`, `ErrorConfiguracion`; enrichment + cache deleted |
| `generar_descripcion.py` | Modified | Groq client/retry/model constants removed; imports shared toolkit |
| `contexto_memoria.py` | Modified | Haiku selector; enrichment step removed; new budget |
| `consultar_documentacion.py` | Modified | Repointed imports and model |
| `prompts.py`, `requirements.txt` | Modified | Dead prompts removed; `groq` dropped; new `qa-documentacion` prompt |
| `app.py` | Modified | Branches on `RespuestaConsulta.tipo` to render answer / clarifying question / no-information distinctly |
| `tests/` (5 files) | Modified | `FakeGroq` → `FakeAnthropic`; SDK-level monkeypatches retargeted; `test_consultar_documentacion.py` asserts 3 return states |
| `openspec/specs/` (4 specs) | Modified/Added | Delta passes per Capabilities, including new `qa-documentacion` domain |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Revised estimate 800–950 changed lines (was 550–750 before `qa-documentacion` was added) exceeds the accepted `size:exception` scope | High | Re-confirmed with user; clean 2-slice cut available: (1) provider migration, Q&A still `str`-returning, (2) `qa-documentacion` behavior — touches only `prompts.py`, `consultar_documentacion.py`, `app.py`, one test file |
| Silent-degrade contracts broken by SDK shape differences (`getattr(exc,"status_code",None)==429`) | Medium | Re-verify against pinned `anthropic>=1.3` at every new call site; keep never-raise tests for `buscar_contexto` and keep-text-on-failure for the verifier |
| 120K budget still truncates an unusually large real doc | Low | Deterministic newline truncation + marker retained; value is a module constant, tunable without code change |
| Input cost rises (raw ≫ summaries) | Medium | Offset by deleting N enrichment calls; selection cap of 3 docs unchanged; measure real token usage post-merge |
| Rename churn inflates the diff | Medium | Do the rename in the first slice, alone, so later slices show clean diffs |

## Rollback Plan

Single revert of the merged commit(s) restores Groq. `groq>=0.11` returns to `requirements.txt` (`pip install -r requirements.txt`); `GROQ_API_KEY` must be present in `.env` again. No data migration, no persisted state — the deleted enrichment cache under `cache/documentacion/` is derived and regenerates itself. Spec deltas revert with the same commit.

## Dependencies

- `ANTHROPIC_API_KEY` becomes the single required LLM key; `GROQ_API_KEY` becomes unused.
- `anthropic>=1.3` (already installed).

## Success Criteria

- [ ] No module or test imports `groq`; `groq` absent from `requirements.txt`.
- [ ] All 4 call sites use `claude-haiku-4-5-20251001` via one shared client/retry helper.
- [ ] Generated tickets cite specifics from full document content (no summary-shaped vagueness) on a real `memory/` corpus.
- [ ] `buscar_contexto()` still never raises with `MEMORY_DIR` missing/unreadable; the verifier still keeps the original text when it fails.
- [ ] Generation and Q&A still fail fast with a clear error when `ANTHROPIC_API_KEY` is absent.
- [ ] `pytest` green from repo root, no network calls, no API key required.
