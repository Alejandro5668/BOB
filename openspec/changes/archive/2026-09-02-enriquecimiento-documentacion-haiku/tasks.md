# Tasks: Haiku-Enriched Documentation Context

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~530 (source ~315, tests ~235, infra ~7) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | Unit 1 → Unit 2 → Unit 3 (see below) |
| Delivery strategy | single-pr |
| Chain strategy | size-exception |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: size-exception
400-line budget risk: High

Delivery strategy is fixed to `single-pr`, so per guard rules the orchestrator
must obtain explicit maintainer `size:exception` approval before `sdd-apply`
runs this as one PR. The work units below are the fallback slicing if the
maintainer instead prefers to override delivery strategy to a stacked chain.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | New unwired module: `contexto_enriquecido.py`, `prompts.py` constants, `requirements.txt`, `Dockerfile`, `docker-compose.yml`, `.gitignore`, `.dockerignore` (~255 lines) | PR 1 | `python -c "import contexto_enriquecido"` | `python -c "from contexto_enriquecido import enriquecer_documentos as e; print(e([]))"` → `[]` | Delete `contexto_enriquecido.py`; revert the 6 infra diffs. Nothing imports the module yet — zero blast radius |
| 2 | `tests/test_contexto_enriquecido.py` — `FakeAnthropic` double + full unit suite for Unit 1 (~180 lines) | PR 2 (parallel-safe with PR 3 once PR 1 merges) | `pytest tests/test_contexto_enriquecido.py -v` | N/A — `FakeAnthropic` double IS the harness; no live network call | Delete the test file only; no production code touched |
| 3 | Wire `contexto_memoria.py::buscar_contexto()` to the enricher + `tests/test_contexto_memoria.py` replacement/new tests + `.env.example` manual task (~95 lines) | PR 3 | `pytest tests/test_contexto_memoria.py -v` | Manual: unset `ANTHROPIC_API_KEY` → identical output to pre-change; set it → `cache/documentacion/` populates, 2nd identical request makes 0 Anthropic calls; `docker compose up` keeps cache after recreation | Revert `contexto_memoria.py`'s one-loop diff → restores verbatim raw blocks exactly (design Rollback Plan) |

## Phase 1: Foundation — New Module

- [x] 1.1 `prompts.py`: append `ENRIQUECEDOR_DOCUMENTACION` (system prompt) and `ENTRADA_ENRIQUECEDOR_DOCUMENTACION` (user template) after `ENTRADA_SELECTOR_DOCUMENTOS`, exact text per design.md lines 384-401. (Spec: documentation-enrichment — Haiku Summarization)
- [x] 1.2 `requirements.txt`: add `anthropic>=1.3` after `groq>=0.11`.
- [x] 1.3 Create `contexto_enriquecido.py` module docstring + imports + constants (`MODELO_ENRIQUECEDOR`, `MAX_TOKENS_ENRIQUECIMIENTO`, `MAX_TRABAJADORES`, `MAX_REINTENTOS_RATE_LIMIT`, `ESPERA_RATE_LIMIT`, `DIRECTORIO_CACHE_POR_DEFECTO`) + `ErrorConfiguracionAnthropic` + `ErrorEnriquecimiento`, verbatim per design.md.
- [x] 1.4 `contexto_enriquecido.py`: `_crear_cliente()` (env-only key check, lazy `Anthropic` import, never logs key value).
- [x] 1.5 `contexto_enriquecido.py`: `_crear_mensaje_con_reintento()` — 429 retry wrapper over `cliente.messages.create`, fixed 5.0s backoff, `MAX_REINTENTOS_RATE_LIMIT` cap.
- [x] 1.6 `contexto_enriquecido.py`: `resolver_directorio_cache()`, `_hash_contenido()` (sha256), `_leer_cache()`, `_escribir_cache()` (tmp file + `Path.replace()` atomic write, `OSError` never raises). (Spec: documentation-enrichment — Content-Addressed Enrichment Cache)
- [x] 1.7 `contexto_enriquecido.py`: `_enriquecer_uno()` — one `messages.create` call, extracts `.content[].text` blocks (NOT Groq's `choices[0].message.content` shape), raises `ErrorEnriquecimiento` on empty text.
- [x] 1.8 `contexto_enriquecido.py`: public `enriquecer_documentos(documentos, *, cliente=None, directorio_cache=None) -> list[str]` — preload raw fallback, cache-hit short-circuit, `ThreadPoolExecutor(max_workers=min(MAX_TRABAJADORES, len(pendientes)))` for misses only, index-keyed futures (never `as_completed`), cache write on main thread after pool closes, per-document exception leaves raw fallback in place. (Spec: documentation-enrichment — Haiku Summarization With Mandatory Raw Fallback; Bounded Concurrent Enrichment Preserving Order)
- [x] 1.9 `Dockerfile`: add `contexto_enriquecido.py` to the explicit `COPY` line (after `contexto_memoria.py`, before `consultar_documentacion.py`).
- [x] 1.10 `docker-compose.yml`: add `- ./cache/documentacion:/app/cache/documentacion` under `volumes:`.
- [x] 1.11 `.gitignore`: add `cache/` between `logs/` and `docker-compose.override.yml`.
- [x] 1.12 `.dockerignore`: add `cache/` between `*.wav` and `*.mp3`.

## Phase 2: Testing — New Module

- [x] 2.1 Create `tests/test_contexto_enriquecido.py`: add `FakeBloqueTexto`, `FakeMensaje`, `FakeMessages`, `FakeAnthropic` doubles verbatim per design.md (mirrors `.content[].text` shape, NOT `FakeGroq`'s). Also added `FakeMessagesPorIndice`/`FakeAnthropicPorIndice` (not in design.md) to support per-document differentiated behavior needed by 2.4/2.6 — see Deviations.
- [x] 2.2 Test: cache hit performs zero `FakeAnthropic` calls; changed content (new hash) triggers a fresh call. (Spec: Content-Addressed Enrichment Cache — both scenarios)
- [x] 2.3 Test: missing `ANTHROPIC_API_KEY` (`monkeypatch.delenv`) returns raw content, never raises. (Spec: Haiku Summarization — Missing API key)
- [x] 2.4 Test: API error for one of several documents degrades only that block; others stay enriched. (Spec: Haiku Summarization — API error for one document among several)
- [x] 2.5 Test: empty Haiku response degrades to raw; unwritable cache directory (`OSError` on `_escribir_cache`) still returns the summary.
- [x] 2.6 Test: order preserved when a later document's call completes first (`FakeAnthropic` sleeping longer for index 0). (Spec: Bounded Concurrent Enrichment Preserving Order)
- [x] 2.7 Run `pytest tests/test_contexto_enriquecido.py -v` — all green before Phase 3. **Result: 11 passed.**

## Phase 3: Integration — `contexto_memoria.py`

- [x] 3.1 Add `Enriquecedor = Callable[[list[tuple[str, str]]], list[str]]` next to `ProveedorContexto` (line 44).
- [x] 3.2 `buscar_contexto()` signature: add `enriquecedor: Optional[Enriquecedor] = None` keyword-only param.
- [x] 3.3 Replace the block-building loop (current lines 335-346): collect `(ruta_relativa, contenido_raw)` pairs in selection order; lazily import `contexto_enriquecido.enriquecer_documentos` as `enriquecedor` when not injected; call it in a try/except that also guards `len(bloques) != len(pares)`, degrading to raw blocks (never `""`) on any failure; pass result to unchanged `_ensamblar_contexto(bloques, PRESUPUESTO_CARACTERES)`. (Spec: context-retrieval — Enriched-or-Raw Context Block Assembly, all 3 scenarios)
- [x] 3.4 Update module docstring: note selected content is passed to `contexto_enriquecido` before assembly.

## Phase 4: Testing — Integration

- [x] 4.1 `tests/test_contexto_memoria.py`: add autouse `_sin_clave_anthropic` fixture (`monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)`) — belt-and-braces guard against any test hitting the real network (no `conftest.py` exists).
- [x] 4.2 Delete `test_buscar_contexto_returns_selected_file_content_verbatim` (lines 337-346) — behavior it asserts (verbatim raw) is no longer true.
- [x] 4.3 Add `test_buscar_contexto_uses_enriched_summary_instead_of_raw_content` — injected `enriquecedor=` lambda returning `f"RESUMEN de {ruta}"`, asserts result AND that the enricher received `(ruta_relativa, contenido_crudo)` pairs in selection order, verbatim per design.md.
- [x] 4.4 Add `test_buscar_contexto_falls_back_to_raw_content_when_enricher_fails` — enricher raises, asserts raw content returned (never `""`).
- [x] 4.5 Add length-mismatch guard test — `enriquecedor=lambda pares: []` → raw content returned, not `""`.
- [x] 4.6 Run `pytest tests/test_contexto_memoria.py -v` — all green, including all pre-existing tests unaffected. **Result: 31 passed, 1 skipped (pre-existing symlink-unsupported skip, unrelated).**

## Phase 5: Manual Task (not automatable)

- [ ] 5.1 **MANUAL STEP — do not automate.** Append `ANTHROPIC_API_KEY=` to `.env.example` (and optionally `CACHE_DOCUMENTACION_DIR=` if the cache path should differ from `./cache/documentacion`). **BLOCKED** — hard-deny on `.env*` paths confirmed again this phase (`Bash cat .env.example` denied by the permission guardrail), same as Fase 1, 2 and 4. Requires manual application outside the agent's write path. Exact lines for the operator to paste:
  ```
  ANTHROPIC_API_KEY=
  CACHE_DOCUMENTACION_DIR=
  ```
  (`CACHE_DOCUMENTACION_DIR` is optional — only needed if the cache path should differ from `./cache/documentacion`.)

## Phase 6: Full Verification

- [x] 6.1 Run full `pytest` from repo root — confirm no regression in `generar_descripcion.py`/`consultar_documentacion.py` call sites (both documented as untouched). **Result: 99 passed, 1 skipped.** `consultar_documentacion.py` imports `buscar_contexto` with no positional args — unaffected by the new keyword-only `enriquecedor` param.
- [ ] 6.2 Manual smoke (documented, not automated): with a real `ANTHROPIC_API_KEY`, first request over a document populates `cache/documentacion/<sha256>.txt`; identical second request makes zero Anthropic calls. **Not run this batch — requires a real key; left for the operator.**
- [ ] 6.3 Manual smoke: `docker compose up`, confirm `cache/documentacion/` persists across container recreation via the new volume. **Not run this batch — left for the operator.**
- [ ] 6.4 Manual smoke: unset `ANTHROPIC_API_KEY` — confirm app behaves exactly as before this change (raw content, no error surfaced to the analyst). **Not run this batch — left for the operator (automated tests already cover the equivalent unit-level fallback behavior via `test_missing_api_key_returns_raw_content_and_never_raises` and the autouse `_sin_clave_anthropic` fixture).**
