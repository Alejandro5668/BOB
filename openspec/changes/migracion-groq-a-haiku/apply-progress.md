# Apply Progress: migracion-groq-a-haiku — PR1 (Phases 1-4)

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

## Status

PR1 (Phases 1-4): **13/13 tasks complete**. All committed locally on
`bob/pr1-migracion-groq-haiku`. `pytest -q` → 99 passed, 1 skipped. Ready for user
review before push/PR. PR2 (Phases 5-8, qa-documentacion) not started — separate later
apply batch, depends on this branch merging to `main` first.
