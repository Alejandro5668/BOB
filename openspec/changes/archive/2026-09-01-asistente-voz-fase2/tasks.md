# Tasks: Module Context Retrieval — Fase 2

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~700-800 |
| 400-line budget risk | High |
| Chained PRs recommended | No |
| Chain strategy | size-exception |
| Delivery strategy | single-pr |

Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: High

single-pr requires maintainer size:exception before sdd-apply. Reference split below only applies if strategy changes.

### Suggested Work Units (reference)

| Unit | Goal | PR | Test cmd | Harness | Rollback |
|---|---|---|---|---|---|
| 1 | memory/ fixture + contexto_memoria.py | PR1 | pytest tests/test_contexto_memoria.py | N/A, pure logic | revert both, no dependents |
| 2 | Wire generar_descripcion.py + app.py | PR2 | pytest tests/test_generar_descripcion.py | streamlit run app.py (E2E blocked on GROQ_API_KEY) | revert diffs, Unit 1 unaffected |
| 3 | requirements.txt/.env.example/README/CLAUDE.md | PR3 | N/A docs | N/A | revert independently |

## Phase 1: memory/ fixture
- [x] 1.1 memory/MEMORY.md index: gestion_riesgos, planes_accion, auditorias_internas per nombre/alias/descripcion regex
- [x] 1.2-1.3 modulos/{gestion_riesgos,planes_accion,auditorias_internas}/_modulo.md
- [x] 1.4 core/arquitectura.md — sentinel CORE_NUNCA_INYECTAR
- [x] 1.5 errores_comunes.md — sentinel ERRORES_NUNCA_INYECTAR
- [x] 1.6 decisiones_tecnicas.md — sentinel DECISIONES_NUNCA_INYECTAR

## Phase 2: contexto_memoria.py core
- [x] 2.1 Constants: TOP_N=2, UMBRAL=0.35, PESO_NOMBRE=0.6, PESO_DESCRIPCION=0.4, PISO_DIFUSO=0.80, SATURACION_DESCRIPCION=3, PRESUPUESTO_CARACTERES=6000
- [x] 2.2 Modulo dataclass, ErrorMemoria
- [x] 2.3 resolver_directorio(): MEMORY_DIR or ./memory
- [x] 2.4 cargar_modulos(): regex parse MEMORY.md, skip bad lines/missing _modulo.md
- [x] 2.5 puntuar(): NFKD normalize, difflib name score w/ PISO_DIFUSO floor, saturated desc overlap

## Phase 3: Path safety (RED→GREEN)
- [x] 3.1 RED: symlink escaping MEMORY_DIR must be rejected
- [x] 3.2 RED: assert zero write/create/delete filesystem calls
- [x] 3.3 GREEN: resolve()-confined reads, only MEMORY.md + modulos/<carpeta>/_modulo.md

## Phase 4: buscar_contexto + diagnosticar
- [x] 4.1 buscar_contexto(): rank (-score,nombre), threshold UMBRAL, top TOP_N, join \n\n
- [x] 4.2 Truncate at PRESUPUESTO_CARACTERES, cut at last \n, append "[contenido truncado]"
- [x] 4.3 diagnosticar(): missing/unreadable → Spanish notice, else None
- [x] 4.4 buscar_contexto never raises; degrade → ""

## Phase 5: generar_descripcion.py
- [x] 5.1 proveedor_contexto kwarg, lazy default = contexto_memoria.buscar_contexto
- [x] 5.2 REGLAS_CONTEXTO + SYSTEM_PROMPT_CON_CONTEXTO (SYSTEM_PROMPT untouched)
- [x] 5.3 PLANTILLA_USUARIO_CON_CONTEXTO with === delimiter (PLANTILLA_USUARIO untouched)
- [x] 5.4 Branch: use *_CON_CONTEXTO only when context non-empty

## Phase 6: app.py
- [x] 6.1 Import diagnosticar
- [x] 6.2 Call diagnosticar() in "Generar descripción" branch before spinner; st.info(aviso) if set

## Phase 7: Config/docs
- [x] 7.1 requirements.txt unchanged
- [ ] 7.2 .env.example: MEMORY_DIR= — MANUAL STEP (Fase 1 permission guardrail blocks automated edit)

  **BLOCKED — same guardrail as Fase 1 task 1.3.** Global Claude Code
  permission settings hard-deny Read/Write/Edit on any `.env*` path
  (confirmed: `Read` on `.env.example` returns "File is in a directory
  that is denied by your permission settings"). This cannot be worked
  around from this session.

  **Human action required:** open `.env.example` manually and add:

  ```
  MEMORY_DIR=./memory
  ```

  (alongside the existing `GROQ_API_KEY=` line from Fase 1). No other
  change needed — `resolver_directorio()` already defaults to `./memory`
  when `MEMORY_DIR` is unset, so the app works without this line too;
  it's documentation-only for local setup clarity.

- [x] 7.3 README.md/CLAUDE.md: memory/ contract + MEMORY_DIR

## Phase 8: Tests
- [x] 8.1 test_contexto_memoria.py: worked example "el módulo donde se ven los riesgos" → gestion_riesgos 0.867
- [x] 8.2 No-match transcript → ""
- [x] 8.3 Two qualifying modules both returned, alphabetical tie-break
- [x] 8.4 Truncation boundary + read-only (no-write) snapshot
- [x] 8.5 Degrade: unset/missing MEMORY_DIR, PermissionError → "" never raises; diagnosticar() message
- [x] 8.6 Scope: injected text excludes core/errores_comunes/decisiones_tecnicas/MEMORY.md sentinels
- [x] 8.7 test_generar_descripcion.py: fake proveedor_contexto — SYSTEM_PROMPT_CON_CONTEXTO+=== vs Fase1 byte-identical

## Status

26/27 tasks complete. Task 7.2 is blocked on the `.env*` permission
guardrail and requires a one-line manual edit by a human collaborator
(see note above). All other tasks are implemented and covered by
passing tests (`pytest` — 31/31 green, including the 12 Fase 1 tests
unmodified in behavior).
