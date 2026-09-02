# Exploration: Retire Groq entirely, move all LLM response-processing to Claude Haiku 4.5

## Current State

**Every Groq call site (3 files, 4 call sites):**
1. `contexto_memoria.py::_preguntar_selector()` (via `elegir_documentos_relevantes`) — `MODELO_SELECTOR = "openai/gpt-oss-20b"`, batched preview-listing selection (`_lotes_de_documentos`, `CARACTERES_POR_LOTE=12000`, no early-stop, cross-batch re-rank above `MAX_ARCHIVOS_SELECCIONADOS=3`), JSON mode, uses `generar_descripcion._crear_completion_con_reintento`.
2. `generar_descripcion.py::generar_descripcion()` — `MODELO = "openai/gpt-oss-120b"`, main ticket-generation call, free-form template text (no JSON mode).
3. `generar_descripcion.py::_verificar_resultado_esperado()` — `MODELO_AUXILIAR = "openai/gpt-oss-20b"`, JSON mode, runs outside the try/except that maps SDK failures to `ErrorGeneracion`, defaults to `True` (keep text) on any failure.
4. `consultar_documentacion.py::responder_consulta()` — reuses `generar_descripcion.MODELO`, `_crear_cliente`, `_crear_completion_con_reintento` directly.

**Groq scaffolding, all owned by `generar_descripcion.py`:** `_crear_cliente()` (`GROQ_API_KEY`, raises FATAL `ErrorConfiguracion` pre-call), `_crear_completion_con_reintento()` (429 retry parsing Groq's `"try again in Xs"` text), `ErrorConfiguracion`/`ErrorGeneracion`. Imported by `contexto_memoria.py` and `consultar_documentacion.py`.

**Existing Anthropic scaffolding already built** in `contexto_enriquecido.py` (today used ONLY for enrichment): `_crear_cliente()` (`ANTHROPIC_API_KEY`, raises NON-fatal `ErrorConfiguracionAnthropic` — "callers degrade to raw content", a different contract than Groq's fatal `ErrorConfiguracion`), `_crear_mensaje_con_reintento()` (same 429 detection, but fixed 5s backoff since Anthropic has no parseable wait-time text), plus a SHA-256 content-addressed cache (`cache/documentacion/<hash>.txt`) and `enriquecer_documentos()` (bounded `ThreadPoolExecutor(max_workers=3)`, order-preserving, total/never-raises). `MODELO_ENRIQUECEDOR = "claude-haiku-4-5-20251001"` already matches the target model id exactly.

**`contexto_memoria.py::buscar_contexto()` pipeline today:** `listar_documentos` → `elegir_documentos_relevantes` (Groq) → read raw content → `enriquecedor(pares)` (lazily → `contexto_enriquecido.enriquecer_documentos`, Haiku) → `_ensamblar_contexto(bloques, PRESUPUESTO_CARACTERES=6000)`. Two independent client-creation chains already coexist in one function (Groq for selection, Anthropic for enrichment) — post-migration these collapse to one provider, but whether the client is threaded through vs. built independently per call site is undecided.

**Budget:** `PRESUPUESTO_CARACTERES=6000` chars (~1500 tokens) was sized for short 4-8 line Haiku summaries, not multi-KB raw `.md` files — will truncate real docs constantly once raw injection replaces enrichment unless raised (Haiku's 200K-token window has ample headroom for 3 raw docs).

**Specs:** `openspec/specs/context-retrieval/spec.md` (needs MODIFIED delta for Groq→Haiku selection + removal of the enrichment requirement), `openspec/specs/documentation-enrichment/spec.md` (needs REMOVED-requirements delta with Reason/Migration if the module is deleted), `openspec/specs/jira-description-generation/spec.md` (already flagged STALE at the top; hardcodes `GROQ_API_KEY`/"Groq API" wording throughout — needs its own MODIFIED delta regardless of this change's rigor).

**Tests needing rewrite:** `tests/test_generar_descripcion.py` and `tests/test_consultar_documentacion.py` (`FakeGroq` shapes, 2 tests monkeypatch `groq_module.Groq` directly, retry tests assert Groq's parseable-wait-text math), `tests/test_contexto_memoria.py` (`FakeGroq`/`FakeGroqSecuencia` for the selector; already has a defensive `_sin_clave_anthropic` autouse fixture that becomes directly load-bearing once selection itself is Anthropic-backed). `tests/test_contexto_enriquecido.py`'s `FakeAnthropic`/`FakeMessages` is already the correct reference shape (`.messages.create` → `.content` list of blocks with `.type`/`.text`) for every migrated call site. `requirements.txt` lists both `groq>=0.11` and `anthropic>=1.3` — `groq` can be dropped once no test imports it.

## Affected Areas
- `generar_descripcion.py` — `MODELO`, `MODELO_AUXILIAR`, `_crear_cliente`, `_crear_completion_con_reintento`, `ErrorConfiguracion`, `ErrorGeneracion`.
- `contexto_memoria.py` — `MODELO_SELECTOR`, `_preguntar_selector`, enrichment step + `_ensamblar_contexto` budget.
- `consultar_documentacion.py` — `MODELO`, imports of Groq-shaped helpers.
- `contexto_enriquecido.py` — deletion vs. repurposing candidate for the shared Anthropic client/retry scaffolding.
- `prompts.py` — `ENRIQUECEDOR_DOCUMENTACION`/`ENTRADA_ENRIQUECEDOR_DOCUMENTACION` become dead if enrichment is removed; static blocks are the user's named caching target but are far smaller than Haiku's cacheable floor.
- `requirements.txt`, and the 3+1 test files above.

## Approaches

1. **Delete `contexto_enriquecido.py`; centralize Anthropic scaffolding in a new module** (e.g. `cliente_anthropic.py`) — Pros: clean naming, obvious single home. Cons: no real reuse target left for the content-addressed cache pattern (transcripts/questions are unique per request); touches 4 files. Effort: Medium.
2. **Slim `contexto_enriquecido.py` to just the reusable client/retry scaffolding**, dropping `enriquecer_documentos`/cache functions, keep it as the shared toolkit all 4 call sites import from — Pros: directly satisfies "reuse the existing scaffolding" with minimum motion. Cons: filename becomes misleading (rename left to design). Effort: Low-Medium.
3. **Leave `contexto_enriquecido.py` untouched, build new client code elsewhere** — rejected outright: violates the explicit "no reingeniería" constraint.

## Recommendation

Approach 2. There is no good reuse target in this codebase for the content-addressed cache pattern once raw injection replaces enrichment (documents are read fresh per query; only document content — not transcripts/questions — repeats, and raw injection removes the need to cache a compressed derivative of it). Fatal-vs-non-fatal exception semantics need explicit reconciliation in the proposal, not assumed here.

## Open Questions for the Proposal Phase

1. **Fatal vs. non-fatal client-creation error** — `ErrorConfiguracion` (fatal) vs. `ErrorConfiguracionAnthropic` (non-fatal) can't collapse into one type without changing a contract.
2. **New raw-context budget** — concrete replacement for `PRESUPUESTO_CARACTERES=6000`, grounded in real `memory/` corpus file sizes, not a guess.
3. **Client sharing** — one Anthropic client threaded through selector+verifier+generation per request, or independently resolved as today?
4. **Prompt caching ROI is likely near-zero as literally requested** — confirmed live via `platform.claude.com/docs`: Haiku 4.5 requires a ~4,096-token minimum per cache breakpoint (vs. 1,024–2,048 for Sonnet/Opus tiers); shorter blocks are silently not cached (verify via `cache_creation_input_tokens`/`cache_read_input_tokens` in the response). The static system prompt + `PLANTILLA_TICKET_JIRA` + rule blocks (`GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO`) is ~4,000 characters (~1,000 tokens) — under that floor. A more promising target: cache the (now much larger) injected raw-context block itself across repeated calls in the same session (e.g. Q&A follow-ups against the same doc set), since that's far more likely to clear 4,096 tokens. Up to 4 explicit breakpoints allowed; `system` must be an array-of-blocks (not a string) for explicit `cache_control`. Cache write costs 1.25x/2x base price (5m/1h TTL); reads cost ~0.1x — needs reuse within the TTL window to net save.
5. **Sequential-call consolidation** — today's flow is selection (1+ calls) → generation → conditional verifier = 2-3+ round trips. Merging verifier into the generation call (self-reported groundedness via structured output) is the most plausible consolidation but risks self-grading reliability vs. a dedicated pass — needs evaluation, not assumption. Merging selection into generation isn't realistic given the real 273-file corpus requires a lightweight preview-only listing to stay cost-bounded.
6. **`contexto_enriquecido.py` rename**, if approach 2 is accepted.
7. **`prompts.py` cleanup** of now-dead enrichment prompt constants.

## Risks
- Caching may not materialize as requested (Open Question 4) — expectation-management risk if not surfaced before design commits to a `cache_control` placement.
- Silent-degrade contracts (`buscar_contexto` never raises; verifier defaults to keep-text on failure) must survive the provider swap exactly — re-verify Anthropic SDK exception shape (`status_code` attribute) at any new call site.
- Real 273-file `memory/` corpus makes the new budget number (Open Question 2) the single highest-impact decision — an under-sized budget silently truncates real documentation exactly where compression didn't, undermining the user's core "more complete analysis" goal.
- Test rewrite surface: 2 tests monkeypatch `groq_module.Groq` at the SDK level directly, not just the client object — need an equivalent Anthropic-SDK-level swap, not just a fake-object substitution.

## Ready for Proposal
Yes — current-state map, every call site, existing reusable scaffolding, and concrete open questions are ready for `sdd-propose`.
