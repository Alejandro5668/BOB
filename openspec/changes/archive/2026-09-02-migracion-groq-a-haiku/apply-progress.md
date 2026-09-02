# Apply Progress: migracion-groq-a-haiku — PR1 (Phases 1-4) + PR2 (Phases 5-8)

**Branch**: `bob/pr1-migracion-groq-haiku` (off `main`). Committed locally only —
NOT pushed, NOT opened as a PR. Awaiting user review before any push.

**Mode**: Standard (strict_tdd: false).

## Completed Tasks (all of PR1, Phases 1-4)

- [x] 1.1-1.5 `cliente_anthropic.py` (renamed from `contexto_enriquecido.py`): slimmed to
      `ErrorConfiguracion`, `_crear_cliente`, `_crear_mensaje_con_reintento`, `_texto_de`,
      `_pedir_json`, `MODELO_HAIKU = "claude-haiku-4-5-20251001"`. All enrichment/cache
      symbols deleted (`enriquecer_documentos`, `_enriquecer_uno`, `ErrorEnriquecimiento`,
      cache read/write/hash helpers, `ErrorConfiguracionAnthropic`).
- [x] 2.1-2.3 `generar_descripcion.py`: imports from `cliente_anthropic`; `MODELO =
      MODELO_AUXILIAR = MODELO_HAIKU`; `_verificar_resultado_esperado` uses `_pedir_json`;
      `generar_descripcion()` builds client first, threads it into a `proveedor_contexto`
      closure over `buscar_contexto(cliente=cliente)`; `ErrorGeneracion` stays local.
- [x] 2.4-2.6 `contexto_memoria.py`: `PRESUPUESTO_CARACTERES = 120_000`; `MODELO_SELECTOR =
      MODELO_HAIKU`; `_preguntar_selector` uses `_pedir_json`; `buscar_contexto()` reads
      selected docs' raw content verbatim (no `enriquecedor=` seam), assembles via
      `_ensamblar_contexto`, keeps the never-raise `except Exception -> ""` contract.
- [x] 2.7 `consultar_documentacion.py`: repoint-only. `MODELO = MODELO_HAIKU`; `system=`/
      `messages=[user]` shape; `responder_consulta()` STILL returns plain `str` (no
      `RespuestaConsulta`, no tag parsing — that's PR2). Client sharing: when `cliente` is
      injected it's threaded into the default `proveedor_contexto` closure; when `cliente`
      is None, no client is hoisted (preserves zero-network-call `SIN_INFORMACION` path).
- [x] 3.1-3.5 Cleanup: `prompts.py` `ENRIQUECEDOR_DOCUMENTACION`/`ENTRADA_ENRIQUECEDOR_DOCUMENTACION`
      deleted + 3 docstrings fixed; `requirements.txt` dropped `groq>=0.11`; `Dockerfile`
      COPY list updated (`cliente_anthropic.py`); `docker-compose.yml` dropped the
      `cache/documentacion` volume line. Confirmed zero `import groq`/`from groq` left
      anywhere in source or tests.
- [x] 4.1-4.6 Testing: `tests/test_contexto_enriquecido.py` -> `tests/test_cliente_anthropic.py`
      (git mv + full rewrite: 11 enrichment/cache tests deleted, 19 scaffolding tests added
      incl. fail-fast x2, `_texto_de` x2, 4 retry tests, `_pedir_json` x3, 2 hygiene tests).
      `test_generar_descripcion.py`, `test_contexto_memoria.py`, `test_consultar_documentacion.py`
      all rewritten `FakeGroq*` -> `FakeAnthropic*` (Anthropic Messages API shape:
      `.messages.create`, `system=` kwarg, `.content` list of text blocks). 3 enrichment
      tests deleted from `test_contexto_memoria.py`, 4 raw-content/budget tests added. 1
      client-sharing test added to `test_consultar_documentacion.py`.

## Files Changed

| File | Action | What Was Done |
|------|--------|---------------|
| `cliente_anthropic.py` | Renamed + rewritten (was `contexto_enriquecido.py`) | Slimmed to shared client/retry/JSON-helper scaffolding |
| `generar_descripcion.py` | Modified | Repointed to Haiku via `cliente_anthropic`; client-sharing closure |
| `contexto_memoria.py` | Modified | Raw-content injection, 120K budget, Haiku selector via `_pedir_json` |
| `consultar_documentacion.py` | Modified | Repoint-only; `str` return unchanged |
| `prompts.py` | Modified | Deleted 2 enrichment prompt constants + fixed 3 docstrings |
| `requirements.txt` | Modified | Dropped `groq>=0.11` |
| `Dockerfile` | Modified | COPY list: `contexto_enriquecido.py` -> `cliente_anthropic.py` |
| `docker-compose.yml` | Modified | Dropped `cache/documentacion` volume |
| `tests/test_cliente_anthropic.py` | Renamed + rewritten (was `test_contexto_enriquecido.py`) | New scaffolding test suite |
| `tests/test_generar_descripcion.py` | Modified | `FakeAnthropic`, `system=`-shaped assertions |
| `tests/test_contexto_memoria.py` | Modified | `FakeAnthropic*`, raw-content tests |
| `tests/test_consultar_documentacion.py` | Modified | `FakeAnthropic`, client-sharing test added |
| `openspec/changes/migracion-groq-a-haiku/tasks.md` | Modified | PR1 Phases 1-4 marked `[x]` |

Not touched (as instructed): `app.py`, `transcribir.py`, `logging_config.py`,
`tests/test_transcribir.py`, `tests/test_logging_config.py`, all Phase 5-8 (PR2) scope.
`.env.example` was already modified (pre-existing uncommitted change from an earlier
session, adding `ANTHROPIC_API_KEY`) — left as-is, out of this PR's task list.

## Work Unit Evidence

| Evidence | Value |
|---|---|
| Focused test command | `pytest tests/test_generar_descripcion.py tests/test_contexto_memoria.py tests/test_consultar_documentacion.py tests/test_cliente_anthropic.py -v` → all passed |
| Full suite | `pytest -q` → **99 passed, 1 skipped** (symlink test, platform-skipped on Windows — pre-existing, unrelated to this change) |
| Runtime harness | Not run (requires real `ANTHROPIC_API_KEY` + manual smoke — deferred to the user before merge, per tasks.md's own "Manual: unset GROQ_API_KEY, set ANTHROPIC_API_KEY..." note) |
| Rollback boundary | Revert the merge commit on `bob/pr1-migracion-groq-haiku`; `groq>=0.11` and `GROQ_API_KEY` requirement return; `contexto_enriquecido.py` restorable via `git mv` reversal |

## Deviations from Design

None in behavior. One necessary test-isolation addition not spelled out verbatim in
design.md: `test_generar_descripcion.py` and `test_consultar_documentacion.py` needed
`MEMORY_DIR` pointed at a nonexistent path (autouse fixture) for every test that doesn't
inject its own `proveedor_contexto`, because design decision 7 (client sharing) threads
the injected `FakeAnthropic` into the default context-retrieval provider — without this,
tests would silently scan the project's real `memory/` folder (which has real `.md`
content) and consume an extra selector call before the generation-call assertions run.
This is a required consequence of decision 7, not a deviation from it.

## Issues Found

`anthropic` package was not installed in the local dev/test environment despite being
pinned in `requirements.txt` (pre-existing gap, unrelated to this PR) — installed it
locally (`pip install "anthropic>=1.3"`) to run the real test suite and confirm a real
pass/fail count rather than assume green.

## Status (PR1 only, superseded by PR2 section below for overall status)

PR1 (Phases 1-4): **13/13 tasks complete**. All committed locally on
`bob/pr1-migracion-groq-haiku`. `pytest -q` → 99 passed, 1 skipped. Ready for user
review before push/PR.

---

# PR2 (Phases 5-8) — `qa-documentacion` intelligence (3-state Q&A)

**Branch**: `bob/pr2-qa-documentacion-inteligente`, created off
`bob/pr1-migracion-groq-haiku` (stacked-to-main chain — targets PR1's branch until PR1
merges, then rebases onto `main`). Committed locally only — NOT pushed, NOT opened as a
PR. Awaiting user review before any push.

**Mode**: Standard (strict_tdd: false).

## Completed Tasks (Phases 5-8, except 8.5)

- [x] 5.1-5.3 `consultar_documentacion.py`: added `TIPO_RESPUESTA = "respuesta"`,
      `TIPO_PREGUNTA_ACLARATORIA = "pregunta_aclaratoria"`, `TIPO_SIN_INFORMACION =
      "sin_informacion"`, `TipoRespuesta = Literal[...]`; frozen `@dataclass
      RespuestaConsulta(texto: str, tipo: TipoRespuesta)` with rationale docstring (not
      NamedTuple: tuple-equality hazard; not an exception: clarifying question is a
      success outcome); pure `_interpretar_respuesta(texto_crudo) -> RespuestaConsulta`
      (`partition("]")`, matches `MARCA_PREGUNTA_ACLARATORIA`/`MARCA_RESPUESTA_DIRECTA`,
      else degrades to `TIPO_RESPUESTA` with the full raw text kept verbatim +
      `logger.warning`).
- [x] 6.1-6.3 `prompts.py`: added `PREFILL_RESPONDEDOR_CONSULTA = "[TIPO:"`,
      `MARCA_RESPUESTA_DIRECTA = "[TIPO:RESPUESTA]"`, `MARCA_PREGUNTA_ACLARATORIA =
      "[TIPO:ACLARACION]"`, each with docstring, immediately above
      `RESPONDEDOR_CONSULTA_DOCUMENTACION`. Rewrote `RESPONDEDOR_CONSULTA_DOCUMENTACION`
      verbatim per design.md: both `[TIPO:...]` markers, "cuándo pedir aclaración" block
      (real ambiguity only, one question max, incomplete docs != ambiguity),
      partial-answer/uncertainty bullets, variability bullet, and **removed** the old
      bullet instructing the model to emit the `SIN_INFORMACION` sentence as its own
      answer — replaced with an explicit ban on that exact sentence outside the true
      no-context state (this is the pre-existing prompt defect the design flagged at the
      old `prompts.py:152`, now fixed). `ENTRADA_RESPONDEDOR_CONSULTA` left unchanged.
      `consultar_documentacion.py`: imported the 3 new prompt constants; rewrote
      `responder_consulta()` — no-context short-circuit returns
      `RespuestaConsulta(SIN_INFORMACION, TIPO_SIN_INFORMACION)` with zero client
      construction (byte-identical text, same zero-network-call contract, just wrapped);
      on context found, calls `_crear_mensaje_con_reintento(system=
      RESPONDEDOR_CONSULTA_DOCUMENTACION, messages=[user, {"role":"assistant","content":
      PREFILL_RESPONDEDOR_CONSULTA}])` and returns
      `_interpretar_respuesta(PREFILL_RESPONDEDOR_CONSULTA + _texto_de(respuesta))`.
      Return annotation is now `-> RespuestaConsulta` (was `str`).
- [x] 7.1-7.4 `app.py`: import block now pulls `TIPO_PREGUNTA_ACLARATORIA,
      TIPO_RESPUESTA, responder_consulta` from `consultar_documentacion`; added
      `tipo_respuesta` session-state init defaulting to `TIPO_RESPUESTA` next to the
      existing `resultado` init; button handler sets `tipo_respuesta = TIPO_RESPUESTA` on
      the ticket branch and unwraps `respuesta.texto`/`respuesta.tipo` on the consulta
      branch (`resultado` stays a plain `str`, `st.text_area` contract unchanged); result
      card gained an `elif tipo_respuesta == TIPO_PREGUNTA_ACLARATORIA:` branch with title
      "BOB necesita una aclaración" and the exact subtitle text from design.md.
      `TIPO_SIN_INFORMACION` deliberately has NO dedicated UI branch (falls through to
      the existing `else` per design — no second widget, no `st.info` banner, no
      auto-resubmission).
- [x] 8.1-8.4 `tests/test_consultar_documentacion.py`: rewritten — every prior assertion
      moved from a bare `str` comparison to `.texto`/`.tipo` (old bare-string assertions
      now fail loudly instead of silently passing). Fakes stay prefill-shaped (canned
      text is `"RESPUESTA] ..."`, not `"[TIPO:RESPUESTA] ..."`). Added 7 state/parse
      tests (`test_request_sends_the_type_tag_prefill_as_the_last_message`,
      `test_respuesta_marker_is_stripped_from_the_analyst_facing_text`,
      `test_aclaracion_marker_returns_a_clarifying_question_state`,
      `test_unknown_marker_degrades_to_respuesta_keeping_the_full_text`,
      `test_missing_marker_degrades_to_respuesta_keeping_the_full_text`,
      `test_a_closing_bracket_inside_the_prose_is_not_mistaken_for_a_marker`,
      `test_the_three_states_are_mutually_exclusive`) + 4 prompt-shape tests
      (`test_prompt_declares_both_type_markers_verbatim`,
      `test_prompt_no_longer_instructs_the_model_to_emit_the_sin_informacion_notice`,
      `test_prompt_requires_signaling_uncertainty_and_variability`,
      `test_prompt_limits_a_clarification_to_one_question`). Ran `pytest -q` from repo
      root — all green.
- [ ] 8.5 Manual smoke — **not executed by this apply batch** (requires a live
      `ANTHROPIC_API_KEY` and interactive `streamlit run app.py` session): specific
      question → answer + "Respuesta" header; deliberately vague question → clarifying
      question + "BOB necesita una aclaración" header; question with no matching docs →
      fixed notice with zero Anthropic calls in `logs/app.log`. Flagged to the user
      before PR2 opens/merges.

## Files Changed (PR2)

| File | Action | What Was Done |
|------|--------|---------------|
| `consultar_documentacion.py` | Modified | Added `RespuestaConsulta`, 3 `TIPO_*` constants, `_interpretar_respuesta`; `responder_consulta()` now returns `RespuestaConsulta` |
| `prompts.py` | Modified | Added 3 tag-protocol constants; rewrote `RESPONDEDOR_CONSULTA_DOCUMENTACION` (clarifying-question ability, uncertainty/variability signaling, banned the reserved `SIN_INFORMACION` sentence outside its own state) |
| `app.py` | Modified | Import + session-state + button-handler + result-card branching on `RespuestaConsulta.tipo` |
| `tests/test_consultar_documentacion.py` | Modified | Rewritten to `.texto`/`.tipo` assertions; 11 new tests (7 state/parse + 4 prompt-shape) |
| `openspec/changes/migracion-groq-a-haiku/tasks.md` | Modified | PR2 Phases 5-8 marked `[x]` (except 8.5, left `[ ]`) |

Not touched (out of PR2 scope): `cliente_anthropic.py`, `generar_descripcion.py`,
`contexto_memoria.py`, `transcribir.py`, `logging_config.py`, `requirements.txt`,
`Dockerfile`, `docker-compose.yml` — all already correct from PR1.

## Work Unit Evidence (PR2)

| Evidence | Value |
|---|---|
| Focused test command | `pytest tests/test_consultar_documentacion.py -v` → **17 passed** |
| Full suite | `pytest -q` → **110 passed, 1 skipped** (same pre-existing symlink skip, unrelated to this change) |
| Runtime harness | Not run — task 8.5 manual smoke requires a live `ANTHROPIC_API_KEY` and interactive UI session; explicitly deferred to the user, not executed by this apply batch |
| Rollback boundary | Revert the commit on `bob/pr2-qa-documentacion-inteligente`; `responder_consulta()` returns to a plain `str`, `app.py`'s result-card branch reverts to its single `else`, `RESPONDEDOR_CONSULTA_DOCUMENTACION` reverts to its pre-PR2 text |

## Deviations from Design (PR2)

None. Implementation matches design.md decisions 15-18 verbatim:
- Decision 15: `RespuestaConsulta` frozen dataclass + 3 `TIPO_*` constants, placed in
  `consultar_documentacion.py`.
- Decision 16/18: assistant-prefilled `[TIPO:...]` tag (not JSON, not a searched
  sentinel) — `PREFILL_RESPONDEDOR_CONSULTA` sent as the last message, structural
  parsing via `partition("]")` on the re-prepended text.
- Decision 17: parse failure (unknown/absent tag) degrades to `TIPO_RESPUESTA` with the
  raw text kept verbatim, never fabricating `TIPO_SIN_INFORMACION`.
- The pre-existing prompt defect at the old `prompts.py:152` (model instructed to emit
  the reserved `SIN_INFORMACION` sentence even when context was found) is fixed exactly
  as design.md's PR2 addendum describes.

One test-design refinement not spelled out verbatim in design.md/tasks.md: the
`test_prompt_no_longer_instructs_the_model_to_emit_the_sin_informacion_notice` test
cannot assert plain absence of the `SIN_INFORMACION` substring from the prompt, because
design.md's own prompt text quotes that exact sentence *inside the ban itself* ("No uses
la frase \"...\": esa frase está reservada..."). The test instead asserts the OLD
instructing pattern (`decilo: "..."`) is gone AND the ban wording ("no uses la frase") is
present — this is the same distinction design.md's own decision table draws (removal of
the *instructing* bullet, replaced by an explicit *ban*), just expressed as two assertions
instead of one substring check.

Also not spelled out verbatim but necessary: `test_the_three_states_are_mutually_exclusive`
exercises all three states through their real runtime paths (two via `_interpretar_respuesta`,
one via `responder_consulta` with an empty context) rather than only checking that the three
constant strings are distinct, since the latter would be tautological and prove nothing about
actual behavior.

## Issues Found (PR2)

None.

## Overall Status

PR1 (Phases 1-4): **13/13 tasks complete**, committed on `bob/pr1-migracion-groq-haiku`.
PR2 (Phases 5-8): **17/18 tasks complete** (all except manual smoke 8.5), committed on
`bob/pr2-qa-documentacion-inteligente` (branched off PR1's branch, per the
stacked-to-main chain). `pytest -q` on PR2's branch → **110 passed, 1 skipped**. Both
branches are local-only, not pushed, not opened as PRs — ready for user review before
any push. Remaining work: task 8.5 manual smoke (needs a live `ANTHROPIC_API_KEY`), and
the archive-time spec-merge task (A.1), which runs after PR2 merges.
