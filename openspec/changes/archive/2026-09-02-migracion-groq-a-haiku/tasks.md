# Tasks: Retire Groq, run all LLM processing on Claude Haiku 4.5

Full decisions/exact file contents: `openspec/changes/migracion-groq-a-haiku/design.md`
(decisions 1-14 = PR1, decisions 15-18 = PR2). Spec deltas:
`openspec/changes/migracion-groq-a-haiku/specs/{context-retrieval,documentation-enrichment,jira-description-generation,qa-documentacion}/spec.md`.

**Delivery (user-confirmed, final)**: 2 chained PRs, `chain_strategy: stacked-to-main`.
`bob/pr1-migracion-groq-haiku` targets `main`; `bob/pr2-qa-documentacion-inteligente`
targets `bob/pr1-migracion-groq-haiku`. PR1 merges to `main` first; PR2 rebases onto
`main` and merges second. Decision already made — no further apply-time decision needed.

---

# PR1 — Provider migration (Groq → Haiku, no Q&A behavior change)

## Review Workload Forecast — PR1

| Field | Value |
|-------|-------|
| Estimated changed lines | ~600-750 (rename/slim `cliente_anthropic.py` ~150, `generar_descripcion.py` ~100, `contexto_memoria.py` ~80, `consultar_documentacion.py` repoint-only ~40, `prompts.py` cleanup ~15, infra ~10, 4 test files ~300-400) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes (already the plan: PR1 of 2) |
| Suggested split | This is already the first of 2 chained PRs. No further split requested by the user; flagged honestly below since it still exceeds the ~400-line session target even as a slice |
| Delivery strategy | user-confirmed stacked-to-main (2 PRs) |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

**Honest flag**: 600-750 lines is still above the 400-line target for a single session
even after already isolating PR1 from PR2. Not forced to fit. If a further cut is
wanted, the natural sub-boundary is 1a = rename/slim + dead-code/infra cleanup
(~250-300 lines, zero call-site behavior change, safest revert boundary) vs.
1b = the 3 call-site repoints + all 4 test-file rewrites (~350-450 lines). Not
adopted here because the user's final delivery decision is exactly 2 PRs.

### Suggested Work Units — PR1

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | `cliente_anthropic.py` shared scaffolding, unwired | PR1 (Phase 1) | `python -c "import cliente_anthropic"` | N/A — no call site imports it yet | Delete the new file + `git mv` revert; nothing imports it |
| 2 | Repoint all 4 call sites + dead-code/infra cleanup | PR1 (Phases 2-3) | `pytest tests/test_generar_descripcion.py tests/test_contexto_memoria.py tests/test_consultar_documentacion.py -v` | Manual: unset `GROQ_API_KEY`, set `ANTHROPIC_API_KEY`, run one real generation + one Q&A — confirm 2-3 Anthropic calls in `logs/app.log`, zero Groq references | Revert the merge commit; `groq>=0.11` returns, `GROQ_API_KEY` required again |
| 3 | Rewrite `FakeGroq`→`FakeAnthropic` across affected test files | PR1 (Phase 4) | `pytest -q` (full suite, no network, no key) | N/A — fakes ARE the harness | Revert test files only; production code unaffected by test-only revert |

## Phase 1: Foundation — `cliente_anthropic.py`

- [x] 1.1 `git mv contexto_enriquecido.py cliente_anthropic.py`; rewrite module docstring per design.md (drops enrichment/cache framing, states `ErrorConfiguracion` is the one missing-key error, fatality is call-site policy).
- [x] 1.2 Delete enrichment/cache symbols: `enriquecer_documentos`, `_enriquecer_uno`, `ErrorEnriquecimiento`, `resolver_directorio_cache`, `_hash_contenido`, `_leer_cache`, `_escribir_cache`, `MODELO_ENRIQUECEDOR`, `MAX_TOKENS_ENRIQUECIMIENTO`, `MAX_TRABAJADORES`, `DIRECTORIO_CACHE_POR_DEFECTO`, `ErrorConfiguracionAnthropic`.
- [x] 1.3 Keep/confirm `MODELO_HAIKU = "claude-haiku-4-5-20251001"`, `MAX_REINTENTOS_RATE_LIMIT = 3`, `ESPERA_RATE_LIMIT = 5.0`, `ErrorConfiguracion`, `_crear_cliente()`, `_crear_mensaje_con_reintento()` verbatim per design.md. (Decisions 1, 6)
- [x] 1.4 Add `_texto_de(respuesta) -> str` — joins `.content` blocks where `.type == "text"`. (Decision 5)
- [x] 1.5 Add `_pedir_json(cliente, *, model, system, mensaje_usuario, max_tokens) -> dict` — assistant prefill `"{"`, `json.JSONDecoder().raw_decode`. (Decision 4, 5)

## Phase 2: Core Implementation — repoint call sites

- [x] 2.1 `generar_descripcion.py`: replace imports/constants per design.md exact block — import from `cliente_anthropic` (`MODELO_HAIKU`, `_crear_cliente`, `_crear_mensaje_con_reintento`, `_pedir_json`, `_texto_de`); `MODELO = MODELO_HAIKU`; `MODELO_AUXILIAR = MODELO_HAIKU`. Delete `import json/os/time`, `_PATRON_ESPERA_RATE_LIMIT`, `MAX_REINTENTOS_RATE_LIMIT`, `_crear_completion_con_reintento`, local `ErrorConfiguracion`, local `_crear_cliente`. (Spec: jira-description-generation — API Key Fail-Fast; Decisions 2, 3, 6)
- [x] 2.2 `generar_descripcion.py`: rewrite `_verificar_resultado_esperado()` to call `_pedir_json(cliente, model=MODELO_AUXILIAR, system=VERIFICADOR_RESULTADO_ESPERADO, ...)`, keep fail-open `except Exception: return True`. (Spec: jira-description-generation — grounding-check failure keeps original text)
- [x] 2.3 `generar_descripcion.py`: rewrite `generar_descripcion()` body — build client, thread into `proveedor_contexto` closure over `buscar_contexto(cliente=cliente)`, call `_crear_mensaje_con_reintento(system=..., messages=[{"role":"user",...}])`, raise `ErrorGeneracion` on failure with reworded message, call `postprocesar_descripcion(_texto_de(respuesta), ...)`. (Decision 7)
- [x] 2.4 `contexto_memoria.py`: replace imports/constants — `from cliente_anthropic import MODELO_HAIKU, _crear_cliente, _pedir_json`; `PRESUPUESTO_CARACTERES = 120_000`; `MODELO_SELECTOR = MODELO_HAIKU`; delete `Enriquecedor` alias and the gpt-oss reasoning-token comment block. (Spec: context-retrieval — Bounded Context Size; Decision 11)
- [x] 2.5 `contexto_memoria.py`: rewrite `_preguntar_selector()` to call `_pedir_json(cliente, model=MODELO_SELECTOR, system=SELECTOR_DOCUMENTOS_RELEVANTES, ...)`; keep `CARACTERES_POR_LOTE = 12000` unchanged. (Spec: context-retrieval — Schema-Free Discovery and Haiku-Assisted Selection; Decision 12)
- [x] 2.6 `contexto_memoria.py`: rewrite `buscar_contexto()` — remove the `enriquecedor=` seam entirely, read each selected path's raw content via `.read_text()`, pass verbatim blocks straight to `_ensamblar_contexto(bloques, PRESUPUESTO_CARACTERES)`, keep the outer `except Exception → ""` never-raise contract. (Spec: context-retrieval — Raw Full-Document Context Block Assembly, both scenarios; Decision 10)
- [x] 2.7 `consultar_documentacion.py`: repoint imports only — `from cliente_anthropic import MODELO_HAIKU, _crear_cliente, _crear_mensaje_con_reintento, _texto_de`; `MODELO = MODELO_HAIKU`; use `system=`/`messages=[{"role":"user",...}]` in the existing `messages.create` call; reword the `ErrorGeneracion` message. **No `RespuestaConsulta`, no tag parsing, no prompt rewrite in this PR** — `responder_consulta()` keeps returning a plain `str`.

## Phase 3: Cleanup — dead code + infra

- [x] 3.1 `prompts.py`: delete `ENRIQUECEDOR_DOCUMENTACION` and `ENTRADA_ENRIQUECEDOR_DOCUMENTACION` + docstrings; update module docstring `"Groq today"` → `"Claude Haiku 4.5 today"`; correct the 3 docstrings that still name Groq. **Do not touch `RESPONDEDOR_CONSULTA_DOCUMENTACION` yet** (PR2 owns that rewrite).
- [x] 3.2 `requirements.txt`: remove `groq>=0.11` line.
- [x] 3.3 `Dockerfile`: update `COPY` list — `contexto_enriquecido.py` → `cliente_anthropic.py`.
- [x] 3.4 `docker-compose.yml`: remove the `./cache/documentacion:/app/cache/documentacion` volume line.
- [x] 3.5 Confirm no remaining `import groq` anywhere in the tree (source + tests) via a repo-wide search before moving to Phase 4.

## Phase 4: Testing — repoint fakes, no behavior assertions changed for Q&A

- [x] 4.1 `git mv tests/test_contexto_enriquecido.py tests/test_cliente_anthropic.py`; keep `FakeBloqueTexto`/`FakeMensaje`/`FakeMessages`/`FakeAnthropic` verbatim; delete all 11 enrichment/cache tests + `FakeMessagesPorIndice`/`FakeAnthropicPorIndice`.
- [x] 4.2 `tests/test_cliente_anthropic.py`: add the 14 scaffolding tests per design.md (missing/blank-key fail-fast, `_crear_cliente` passes key, `_texto_de` x2, 4 retry tests with fixed 5.0s wait, `_pedir_json` prefill/trailing-text/bad-json x3, `test_no_module_or_test_imports_groq`, `test_requirements_no_longer_lists_groq`).
- [x] 4.3 `tests/test_generar_descripcion.py`: drop `FakeGroq`/`FakeChoice`/`FakeResponse`/`FakeCompletions`/`FakeChat` + rate-limit fakes; add `FakeAnthropic` variant discriminating on `system` (not `model` — `MODELO == MODELO_AUXILIAR` now); replace the `response_format` assertion with `system == VERIFICADOR_RESULTADO_ESPERADO` + `messages[-1] == {"role":"assistant","content":"{"}`; move the 4 retry tests to `test_cliente_anthropic.py`; delete the wait-text-parsing retry test (no Anthropic equivalent).
- [x] 4.4 `tests/test_contexto_memoria.py`: replace `FakeGroq*` family with `FakeAnthropicSecuencia`/`FakeMessagesSeleccion`; delete `test_buscar_contexto_uses_enriched_summary_instead_of_raw_content`, `..._falls_back_to_raw_content_when_enricher_fails`, `..._falls_back_to_raw_content_on_enricher_length_mismatch`; add `test_buscar_contexto_returns_selected_file_content_verbatim`, `..._concatenates_selected_docs_in_selection_order`, `..._injects_a_large_document_whole_under_the_new_budget` (40KB doc, asserts `MARCADOR_TRUNCADO not in contexto`), `..._degrades_to_empty_when_key_missing_and_no_client_injected`. (Spec: context-retrieval — all 4 scenarios above)
- [x] 4.5 `tests/test_consultar_documentacion.py`: `FakeGroq`→`FakeAnthropic` only; rename `test_groq_failure_raises_error_generacion_with_friendly_message`→`test_anthropic_failure_...`; keep every assertion as a bare `str` comparison (no `.texto`/`.tipo` yet — that is PR2's breaking change); add `test_injected_client_is_shared_with_the_default_context_provider`.
- [x] 4.6 Run `pytest -q` from repo root — all green, no network calls, no API key required, zero `groq` references anywhere in the run.

**PR1 status: all Phase 1-4 tasks complete.** Final local run: `pytest -q` → 99 passed, 1 skipped
(symlink test, skipped on this Windows environment — unrelated to this change). Committed on
branch `bob/pr1-migracion-groq-haiku`, not yet pushed/opened as a PR.

---

# PR2 — `qa-documentacion` intelligence (3-state Q&A)

Depends on PR1 merged (same files, `cliente_anthropic.py` already in place). Branch
`bob/pr2-qa-documentacion-inteligente` targets `bob/pr1-migracion-groq-haiku` until PR1
merges, then rebases onto `main` before opening the PR.

## Review Workload Forecast — PR2

| Field | Value |
|-------|-------|
| Estimated changed lines | ~150-200 (prompt rewrite ~35, `consultar_documentacion.py` ~60, `app.py` ~20, `tests/test_consultar_documentacion.py` ~70-90) |
| 400-line budget risk | Low |
| Chained PRs recommended | No further split needed within PR2 |
| Suggested split | Single PR (2nd of the 2-PR chain) |
| Delivery strategy | user-confirmed stacked-to-main (2 PRs) |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: stacked-to-main
400-line budget risk: Low

### Suggested Work Units — PR2

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | `RespuestaConsulta` dataclass + tag parser + prompt rewrite + `app.py` branching + test rewrite (all one deliverable — return-contract break) | PR2 | `pytest tests/test_consultar_documentacion.py -v` | Manual: specific question → "Respuesta" header; vague question → "BOB necesita una aclaración" header; no-match question → fixed notice, zero Anthropic calls in `logs/app.log` | Revert the merge commit; `responder_consulta()` returns to plain `str`, `app.py` result-card branch reverts to its single `else` |

## Phase 5: Foundation — return-contract types

- [x] 5.1 `consultar_documentacion.py`: add `from dataclasses import dataclass`, `from typing import Literal`; add `TIPO_RESPUESTA = "respuesta"`, `TIPO_PREGUNTA_ACLARATORIA = "pregunta_aclaratoria"`, `TIPO_SIN_INFORMACION = "sin_informacion"`, `TipoRespuesta = Literal[...]` next to `SIN_INFORMACION`. (Design decision 15)
- [x] 5.2 `consultar_documentacion.py`: add frozen `@dataclass class RespuestaConsulta: texto: str; tipo: TipoRespuesta` with docstring explaining why NOT a `NamedTuple` (tuple-equality hazard) and why NOT an exception (clarifying question is a success outcome). (Design decision 15)
- [x] 5.3 `consultar_documentacion.py`: add pure `_interpretar_respuesta(texto_crudo: str) -> RespuestaConsulta` — `partition("]")`, match `MARCA_PREGUNTA_ACLARATORIA`/`MARCA_RESPUESTA_DIRECTA`, else degrade to `TIPO_RESPUESTA` with the full raw text kept verbatim + a `logger.warning`. (Design decision 17; Spec: qa-documentacion — No-Information Degrade Stays Distinct From Uncertainty)

## Phase 6: Core Implementation — prompt + request wiring

- [x] 6.1 `prompts.py`: add `PREFILL_RESPONDEDOR_CONSULTA = "[TIPO:"`, `MARCA_RESPUESTA_DIRECTA = "[TIPO:RESPUESTA]"`, `MARCA_PREGUNTA_ACLARATORIA = "[TIPO:ACLARACION]"` immediately above `RESPONDEDOR_CONSULTA_DOCUMENTACION`, each with docstring per design.md. (Design decision 16, 18)
- [x] 6.2 `prompts.py`: rewrite `RESPONDEDOR_CONSULTA_DOCUMENTACION` verbatim per design.md — adds the two literal `[TIPO:...]` markers, the "cuándo pedir aclaración" block (one question max, incomplete docs ≠ ambiguity), the partial-answer/uncertainty-signaling bullets, the variability-signaling bullet, and **removes** the old bullet instructing the model to emit the `SIN_INFORMACION` sentence — replaced by an explicit ban on that exact sentence. `ENTRADA_RESPONDEDOR_CONSULTA` stays unchanged. (Spec: qa-documentacion — Plain-Language Non-Technical Answers, Uncertainty and Variability Signaling both scenarios, Clarifying Question on Ambiguous Query both scenarios, No-Information Degrade Stays Distinct From Uncertainty)
- [x] 6.3 `consultar_documentacion.py`: import the 3 new prompt constants; rewrite `responder_consulta()` body — no-context short-circuit returns `RespuestaConsulta(SIN_INFORMACION, TIPO_SIN_INFORMACION)` with zero client construction; on context found, build client, call `_crear_mensaje_con_reintento(system=RESPONDEDOR_CONSULTA_DOCUMENTACION, messages=[user, {"role":"assistant","content":PREFILL_RESPONDEDOR_CONSULTA}])`; return `_interpretar_respuesta(PREFILL_RESPONDEDOR_CONSULTA + _texto_de(respuesta))`. Return annotation becomes `-> RespuestaConsulta`. (Design decision 7, 16, 17; Spec: qa-documentacion — Full Raw-Context Grounding, No-Information Degrade scenario 1)

## Phase 7: Integration — `app.py` branching

- [x] 7.1 `app.py`: update import block — `from consultar_documentacion import TIPO_PREGUNTA_ACLARATORIA, TIPO_RESPUESTA, responder_consulta`.
- [x] 7.2 `app.py`: add `if "tipo_respuesta" not in st.session_state: st.session_state.tipo_respuesta = TIPO_RESPUESTA` next to the existing `resultado` init.
- [x] 7.3 `app.py`: button handler — ticket branch sets `st.session_state.tipo_respuesta = TIPO_RESPUESTA`; consulta branch does `respuesta = responder_consulta(...)`, `st.session_state.resultado = respuesta.texto`, `st.session_state.tipo_respuesta = respuesta.tipo`.
- [x] 7.4 `app.py`: result card — add `elif st.session_state.tipo_respuesta == TIPO_PREGUNTA_ACLARATORIA:` branch with title `"BOB necesita una aclaración"` and the exact subtitle text per design.md. Leave `TIPO_SIN_INFORMACION` with no dedicated UI branch (falls through to the existing `else`, per design — states stay distinguishable at the `.tipo` API boundary and via the notice's fixed text). Do not add a second widget, `st.info` banner, or auto-resubmission.

## Phase 8: Testing — 3-state contract + prompt shape

- [x] 8.1 `tests/test_consultar_documentacion.py`: move every existing assertion from a bare `str` comparison to `.texto`/`.tipo` (the return-type break must be LOUD — `assert resultado == SIN_INFORMACION` must fail, not silently pass). Fakes stay prefill-shaped: canned text is `"RESPUESTA] ..."`, not `"[TIPO:RESPUESTA] ..."`.
- [x] 8.2 Add the 7 state/parse tests: `test_request_sends_the_type_tag_prefill_as_the_last_message`, `test_respuesta_marker_is_stripped_from_the_analyst_facing_text`, `test_aclaracion_marker_returns_a_clarifying_question_state`, `test_unknown_marker_degrades_to_respuesta_keeping_the_full_text`, `test_missing_marker_degrades_to_respuesta_keeping_the_full_text`, `test_a_closing_bracket_inside_the_prose_is_not_mistaken_for_a_marker`, `test_the_three_states_are_mutually_exclusive`. (Spec: qa-documentacion — all 8 scenarios collectively)
- [x] 8.3 Add the 4 prompt-shape tests: `test_prompt_declares_both_type_markers_verbatim`, `test_prompt_no_longer_instructs_the_model_to_emit_the_sin_informacion_notice`, `test_prompt_requires_signaling_uncertainty_and_variability`, `test_prompt_limits_a_clarification_to_one_question`.
- [x] 8.4 Run `pytest -q` from repo root — all green, no network calls, no API key required.
- [ ] 8.5 Manual smoke (documented, not automated — `app.py` has no test file and none is added): specific question → answer + "Respuesta" header; deliberately vague question → clarifying question + "BOB necesita una aclaración" header; question with no matching docs → fixed notice with zero Anthropic calls in `logs/app.log`. (Not executed by this apply batch — requires a live `ANTHROPIC_API_KEY` and manual UI interaction; flagged for the user before PR2 opens/merges.)

---

## Archive-time task (do not execute now)

- [ ] A.1 At archive time (after PR2 merges): merge the 4 delta specs already written in
      `openspec/changes/migracion-groq-a-haiku/specs/{context-retrieval,documentation-enrichment,jira-description-generation,qa-documentacion}/spec.md`
      into the corresponding main `openspec/specs/*` files — `documentation-enrichment`
      is a full REMOVE (retire the capability), the other 3 are MODIFY/ADD. This is the
      standard SDD archive step and is not redone here.
