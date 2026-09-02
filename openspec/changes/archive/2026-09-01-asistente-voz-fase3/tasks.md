# Tasks: Structured Markdown Ticket Output — Fase 3

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~400-450 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1: prompts.py + import rewiring → PR2: post-processor + remaining tests + docs |
| Delivery strategy | single-pr |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | `prompts.py` + `generar_descripcion.py` import rewiring + prompt/template/sub-module tests | PR 1 | `pytest tests/test_generar_descripcion.py -k "prompt or template or submodulo"` | N/A — `GROQ_API_KEY` unprovisioned; manual smoke test is explicit follow-up (design Open Questions) | Revert `prompts.py` + import edits restores Fase 2 prose byte-for-byte |
| 2 | Post-processor + blocklist + remaining tests + docs | PR 2 | `pytest tests/test_generar_descripcion.py -k "postproc or relleno or ast"` | N/A — same reason | Drop the `postprocesar_descripcion(...)` wrapper on the return statement |

## Phase 1: prompts.py module (satisfies "Centralized Prompt Repository")

- [x] 1.1 Create `prompts.py`; add `PLANTILLA_TICKET_JIRA` (locked Markdown skeleton) + attribute docstring.
- [x] 1.2 Add `GENERADOR_DESCRIPCION_TICKET` (rules 1-12: r5 explicit MUST NOT invent expectation, r6 `Módulo afectado: no identificado` fallback, r12 no-fence/no-preamble) + docstring.
- [x] 1.3 Add `REGLAS_CONTEXTO_MODULO` (rules 13-18) + `GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO` (concatenation) + docstrings.
- [x] 1.4 Add `ENTRADA_GENERADOR_DESCRIPCION` and `ENTRADA_GENERADOR_DESCRIPCION_CON_CONTEXTO` user-message templates + docstrings.

## Phase 2: Rewire generar_descripcion.py imports (depends on Phase 1)

- [x] 2.1 Import the 4 prompt constants from `prompts`; delete all inline prompt text — no back-compat aliases for `SYSTEM_PROMPT`/`PLANTILLA_USUARIO`/`*_CON_CONTEXTO`.
- [x] 2.2 Confirm `MODELO`, temperature 0.2, `max_tokens` 1024, `ProveedorContexto`, `_crear_cliente`, both error types, and both seams remain untouched.

## Phase 3: Post-processor + blocklist (can start in parallel with Phase 1; 3.6 lands after Phase 2)

- [x] 3.1 Add `ENCABEZADO_RESULTADO` and `AVISO_RESULTADO_NO_CONFIABLE` constants to `generar_descripcion.py`.
- [x] 3.2 Add `FRASES_GENERICAS` blocklist (~55 normalized phrases, 3 categories per design: expectativa con verbo, sin verbo, lado obtenido genérico).
- [x] 3.3 Add scaffolding-prefix stripping regexes (result-prefix, expectation-verb, generic subject, connector).
- [x] 3.4 Implement `es_relleno_generico()`: digit/backtick/quoted-run short-circuit → False; fragment split on `\n .;` and list markers; exact-residue match against blocklist.
- [x] 3.5 Implement `postprocesar_descripcion()`: non-str/blank passthrough; whole-output fence strip; heading locate (no-op if absent); empty or filler body → notice; genuine body unchanged.
- [x] 3.6 Wrap the Groq response with `postprocesar_descripcion(...)` on the return statement, placed OUTSIDE the try/except that maps SDK failures to `ErrorGeneracion`.

## Phase 4: Tests (depends on Phases 2 and 3)

- [x] 4.1 Update `tests/test_generar_descripcion.py` imports to source prompt constants from `prompts`.
- [x] 4.2 Assert both system prompts embed `PLANTILLA_TICKET_JIRA` verbatim, 4 headings in fixed order, r5 MUST NOT wording, r3-4 omission wording, r6 `Módulo afectado: no identificado` literal, r12 no-fence/no-preamble wording.
- [x] 4.3 Assert prompt selection: no context → exactly `GENERADOR_DESCRIPCION_TICKET`; context present → exactly `_CON_CONTEXTO`, startswith base, contains rules 13-18.
- [x] 4.4 Add sub-module naming test using inline `CONTEXTO_SUBMODULO_SINTETICO` + `proveedor_contexto=lambda t: ...` seam (do NOT edit `memory/modulos/gestion_riesgos/_modulo.md`); assert verbatim passthrough inside `===` and `Módulo > Submódulo` rule text present.
- [x] 4.5 Add post-processor unit tests, table-driven: filler → notice (heading kept); genuine expectation → byte-identical; absent section → whole text byte-identical (no-op); empty body → notice; wrapping fence stripped, inner fence kept; mixed genuine+filler body → unchanged.
- [x] 4.6 Add `ast.parse`-based scan asserting no module-level str constant >~120 chars remains in `generar_descripcion.py` (no inline prompt text).
- [x] 4.7 Re-verify Fase 1/2 regression assertions: r9/r10 wording, `---`/`===` delimiters, `ErrorConfiguracion` fail-fast, byte-identical no-context request, FakeGroq canned response round-trips through `postprocesar_descripcion` unchanged.

## Phase 5: Verify + docs

- [x] 5.1 Run full suite (`tests/test_transcribir.py`, `tests/test_contexto_memoria.py`, `tests/test_generar_descripcion.py`); confirm `app.py` needs no changes — it imports only `generar_descripcion`, `ErrorConfiguracion`, `ErrorGeneracion`.
- [x] 5.2 Update `README.md`: template output shape + `prompts.py` module note.
- [x] 5.3 Update `CLAUDE.md`: document the prompt repository convention (`prompts.py`). Already present in the working tree from an earlier phase (uncommitted) — verified content matches the requirement; no further edit needed.
- [x] 5.4 Note only (no action here): `openspec/specs/jira-description-generation/spec.md` delta is applied at archive time, not during apply.
