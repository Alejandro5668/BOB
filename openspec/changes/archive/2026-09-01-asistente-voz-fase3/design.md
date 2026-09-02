# Design: Structured Markdown Ticket Output — Fase 3

## Technical Approach

Two moves, both inside the existing Fase 1/2 topology (`app.py` → domain modules, never the reverse; no domain module imports `streamlit`):

1. **Prompt repository.** A new root-level `prompts.py` holds every prompt constant as a named, documented literal (CLAUDE.md "Prompt repository convention"). `generar_descripcion.py` imports them and defines **no** prompt text. Single file, not a package — one AI feature exists today.
2. **Locked template + best-effort post-processor.** The system prompt carries the literal Markdown skeleton as a **format anchor** (exploration Approach 2) so the model copies a shape instead of interpreting a description. A pure post-processor then runs over the raw response as defense-in-depth against the single known failure shape (a hallucinated generic expectation) plus a wrapping code fence.

The prompt is the **primary** control. The post-processor is best-effort and tuned to prefer false negatives over false positives (see "Blocklist" below).

## Architecture Decisions

### Decision: the skeleton is a literal constant embedded in both system prompts

**Choice**: `PLANTILLA_TICKET_JIRA` is its own constant, interpolated once into `GENERADOR_DESCRIPCION_TICKET` at import time. Tests assert against the constant, never a re-typed copy.
**Alternatives**: describing the sections in prose (Fase 1/2 style — no anchor to copy); duplicating the skeleton text in each system prompt (two literals drift).
**Rationale**: one source of truth for the shape; a template edit cannot desynchronise the context/no-context prompts, and the assertion "the prompt contains the exact template" stays trivially true.

### Decision: prompt rule numbering stays continuous across the two prompts

**Choice**: base prompt owns rules 1–12; `REGLAS_CONTEXTO_MODULO` continues at 13–18 and is appended only when context exists (Fase 2 decision, unchanged).
**Alternatives**: restarting context rules at 1.
**Rationale**: Fase 2 already established continuous numbering (8–12); two rules called "1" in one system message is itself an ambiguity the model can exploit. `GENERADOR_DESCRIPCION_TICKET` stays byte-identical when no context is retrieved.

### Decision: the module fallback body is the full literal `Módulo afectado: no identificado`

**Choice**: under the `## Módulo afectado` heading, the fallback body repeats the label verbatim, exactly as the spec pins it.
**Alternatives**: a bare `no identificado` body (reads better under the heading).
**Rationale**: the spec pins the literal string; an exact-substring assertion in tests and a grep-able marker in Jira beat the mild redundancy. Accepted cost, recorded here so it is not "fixed" later by accident.

### Decision: post-processor lives in `generar_descripcion.py`, not `prompts.py`, and is not injected

**Choice**: `postprocesar_descripcion(texto)` and its blocklist data live next to the Groq call. `prompts.py` holds prompt text only. The function is called directly on the response — no `postprocesar=None` seam.
**Alternatives**: putting the notice/blocklist in `prompts.py` (they are output text and matcher data, not prompts — it would dilute the repository's single purpose); a third injection seam mirroring `cliente` / `proveedor_contexto`.
**Rationale**: the existing seams exist because those collaborators are **impure** (network, filesystem). A pure, total `str -> str` function is directly unit-testable with zero injection. Proposal's partial rollback ("disable the post-processor call") is a one-line edit either way.

### Decision: no back-compat aliases for the old constant names

**Choice**: `SYSTEM_PROMPT`, `PLANTILLA_USUARIO`, `SYSTEM_PROMPT_CON_CONTEXTO`, `PLANTILLA_USUARIO_CON_CONTEXTO` are removed, not aliased. Tests import from `prompts`.
**Rationale**: the spec's "no inline prompt text" scenario is asserted with an `ast` scan for long module-level string constants; leftover aliases keep a second name alive for a prompt that no longer says what its old name claimed (`SYSTEM_PROMPT` was "prosa libre"). `app.py` imports only `generar_descripcion`, `ErrorConfiguracion`, `ErrorGeneracion` — **unaffected**.

### Decision: sub-module coverage via an inline synthetic context string, not a fixture edit

**Choice**: `tests/test_generar_descripcion.py` defines a module-level `CONTEXTO_SUBMODULO_SINTETICO` documenting a `Matriz de riesgos` sub-module, injected with `proveedor_contexto=lambda t: CONTEXTO_SUBMODULO_SINTETICO`.
**Alternatives**: appending a `## Submódulos` block to `memory/modulos/gestion_riesgos/_modulo.md` — mutates a fixture asserted byte-for-byte by `tests/test_contexto_memoria.py` (it reads the file and compares), and pretends the real Kawak `memory/` has a shape nobody confirmed.
**Rationale**: keeps `contexto_memoria.py` and its fixture out of scope (proposal), and the seam already exists. What is *testable today* is that the sub-module naming rule reaches the model verbatim and that the context text is passed through unaltered — model compliance stays a manual smoke test (no `GROQ_API_KEY`).

## `prompts.py` — Contents

Constants are documented with PEP 258 attribute docstrings (a string literal immediately after the assignment), so each prompt carries its role inline.

```python
"""Prompt repository — every LLM prompt used by BOB lives here as a named constant.

See CLAUDE.md "Prompt repository convention". One module today; split into a
`prompts/` package only when a second, unrelated AI feature needs its own prompts.
"""

PLANTILLA_TICKET_JIRA = """## Módulo afectado
<nombre del módulo afectado, o exactamente: Módulo afectado: no identificado>

## Qué pasó
<qué hacía la persona y qué ocurrió, en prosa llana>

## Pasos para reproducir
<solo si el analista narró los pasos; una acción por línea, numeradas>

## Resultado esperado vs. obtenido
<solo si el analista dijo qué esperaba; qué esperaba y qué obtuvo en su lugar>"""
"""Esqueleto Markdown bloqueado del ticket. Se incrusta literal en los prompts de
sistema como ancla de formato: el modelo copia la forma, no la interpreta."""
```

```python
GENERADOR_DESCRIPCION_TICKET = f"""Eres un asistente que redacta descripciones de incidencias para tickets de Jira, en español.

Responde SIEMPRE con esta plantilla, copiando los encabezados carácter por carácter:

{PLANTILLA_TICKET_JIRA}

Reglas obligatorias:
1. Usa exactamente esos encabezados `##`, en ese orden. No añadas, renombres, traduzcas ni reordenes ninguno.
2. `## Módulo afectado` y `## Qué pasó` están SIEMPRE presentes.
3. `## Pasos para reproducir` y `## Resultado esperado vs. obtenido` son opcionales: si el analista no narró los pasos, o no dijo qué esperaba, ELIMINA de la respuesta ese encabezado Y su contenido.
4. PROHIBIDO rellenar una sección omitida con «no especificado», «no aplica», «sin datos», «pendiente», guiones o cualquier otro marcador de posición: la sección simplemente no aparece.
5. PROHIBIDO inventar un resultado esperado. Si el analista no dijo explícitamente qué esperaba que ocurriera, la sección `## Resultado esperado vs. obtenido` NO EXISTE en tu respuesta. No la deduzcas de lo que el sistema «debería» hacer, ni escribas expectativas genéricas del tipo «se esperaba que funcionara correctamente».
6. Si no puedes identificar el módulo afectado, escribe exactamente `Módulo afectado: no identificado` como cuerpo de la primera sección. Nunca omitas esa sección ni inventes un nombre de módulo.
7. Usa lenguaje llano, comprensible para una persona no técnica.
8. Usa ÚNICAMENTE la información presente en la transcripción. No inventes datos.
9. PROHIBIDO mencionar o suponer detalles de implementación (nombres de clases, funciones, métodos, tablas, endpoints, consultas SQL) que no aparezcan literalmente en la transcripción.
10. PROHIBIDO diagnosticar la causa técnica. Describe solo el comportamiento observado: qué hacía la persona, qué esperaba y qué ocurrió.
11. Si un dato no está en la transcripción (versión, usuario, entorno, pasos exactos), omítelo; no lo supongas ni pongas marcadores de posición.
12. Responde solo con la plantilla rellenada: sin preámbulo, sin comentarios finales y SIN envolverla en un bloque de código (nada de ```)."""
"""Prompt de sistema del generador de descripciones de ticket (sin contexto de módulo).
Se usa cuando la recuperación de Fase 2 no devolvió ningún módulo."""
```

Rules 9 and 10 keep their Fase 1 wording verbatim, so the existing prompt assertions in `tests/test_generar_descripcion.py` survive the rewrite unchanged.

```python
REGLAS_CONTEXTO_MODULO = """Reglas adicionales para el bloque "Contexto de módulo":
13. El contexto es documentación interna de referencia. Úsalo SOLO para nombrar correctamente el módulo afectado en `## Módulo afectado` y para usar su vocabulario documentado.
14. Si el contexto documenta submódulos, pantallas o secciones dentro del módulo, nombra en `## Módulo afectado` el más específico que concuerde con la transcripción, con el formato `Módulo > Submódulo`. Si ninguno concuerda, nombra solo el módulo.
15. La transcripción es la única fuente de los hechos del incidente. PROHIBIDO presentar contenido del contexto como algo que ocurrió, se observó o se hizo.
16. PROHIBIDO afirmar o insinuar cualquier cosa sobre el módulo que no aparezca literalmente en el bloque de contexto.
17. Si el contexto no concuerda con lo narrado en la transcripción, IGNÓRALO por completo y redacta únicamente desde la transcripción; si así no puedes nombrar el módulo, escribe `Módulo afectado: no identificado`.
18. PROHIBIDO enumerar funcionalidades del módulo, copiar frases del contexto, mencionar que existe un contexto, o usar el contexto para inventar pasos de reproducción o un resultado esperado."""
"""Reglas 13-18: se anexan al prompt de sistema SOLO cuando hay contexto de módulo.
Reglas sobre un bloque inexistente son en sí mismas un vector de invención."""

GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO = (
    GENERADOR_DESCRIPCION_TICKET + "\n\n" + REGLAS_CONTEXTO_MODULO
)
"""Prompt de sistema del generador cuando la recuperación de Fase 2 sí devolvió
un módulo. Idéntico al base más las reglas de uso del contexto."""
```

Rule 18's new clause ("ni usar el contexto para inventar pasos o un resultado esperado") closes the context-as-invention vector that the two new optional sections would otherwise open.

```python
ENTRADA_GENERADOR_DESCRIPCION = """Transcripción del analista:
---
{transcripcion}
---
Redacta la descripción con la plantilla indicada. Omite por completo las secciones opcionales que el analista no haya mencionado."""
"""Mensaje de usuario del generador sin contexto. Se formatea con `transcripcion`."""

ENTRADA_GENERADOR_DESCRIPCION_CON_CONTEXTO = """Contexto de módulo (documentación interna, solo referencia):
===
{contexto}
===
Transcripción del analista:
---
{transcripcion}
---
Redacta la descripción con la plantilla indicada. Los hechos salen solo de la transcripción; el contexto solo sirve para nombrar el módulo afectado. Omite por completo las secciones opcionales que el analista no haya mencionado."""
"""Mensaje de usuario del generador con contexto. Se formatea con `contexto` y
`transcripcion`. `===` delimita el contexto; `---` la transcripción (Fase 2)."""
```

## Blocklist — Pinned Generic-Filler Phrases

The matcher normalises the fragment first: NFKD accent-strip → lowercase → strip Markdown bullets/bold/backticks → collapse whitespace → strip trailing `.,;:!` (reusing the `_normalizar` idiom already in `contexto_memoria.py`). All phrases below are written in that normalised form (no accents).

```python
FRASES_GENERICAS = frozenset({
    # -- Expectativa genérica: "debía ir bien" (lado esperado) --------------
    "funcionara correctamente", "funcionase correctamente", "funcione correctamente",
    "funcionara con normalidad", "funcionara de manera normal", "funcionara normalmente",
    "funcionara sin errores", "funcionara sin problemas", "funcionara sin inconvenientes",
    "operara con normalidad", "se comportara con normalidad", "se comportara correctamente",
    "cargara correctamente", "se cargara correctamente", "se mostrara correctamente",
    "se guardara correctamente", "se ejecutara correctamente", "se completara correctamente",
    "se procesara correctamente", "respondiera correctamente",
    "no presentara errores", "no presentara ningun error", "no fallara", "no diera error",
    "todo funcionara correctamente", "todo funcionara bien", "todo saliera bien",
    # -- Expectativa genérica sin verbo -------------------------------------
    "un funcionamiento normal", "un comportamiento normal", "el funcionamiento esperado",
    "el comportamiento esperado", "el resultado esperado",
    "sin errores", "sin problemas", "sin inconvenientes", "sin fallos", "sin novedad",
    "de manera normal", "de forma normal", "con normalidad", "correctamente",
    # -- Lado obtenido genérico (no aporta información) ----------------------
    "no funciono correctamente", "no funciono como se esperaba", "no funciono",
    "no ocurrio lo esperado", "no se obtuvo el resultado esperado",
    "el resultado no fue el esperado", "el resultado fue distinto al esperado",
    "se obtuvo un resultado inesperado", "un comportamiento inesperado",
    "ocurrio un error", "se presento un error", "hubo un error", "hubo un fallo",
    "presento un error", "arrojo un error", "fallo",
})
```

**Why these and not others.** Each entry is a statement that would be equally true of *any* incident in *any* module — it carries zero transcript-specific information. Anything naming an object, a count, a screen, a value, or an actual observed behaviour is deliberately absent. Bare `correctamente`, `fallo` and `sin errores` are included **only** because they are matched against a whole fragment (below), never as substrings — `exportara correctamente los 300 riesgos filtrados` never matches.

**Scaffolding stripped before matching** (iteratively, from the fragment start, until stable):

```python
_ANDAMIO = (
    r"(?:el\s+|la\s+)?(?:resultado\s+)?(?:esperado|obtenido|se\s+obtuvo)\s*[:\-]?\s*"
    r"|(?:se\s+)?(?:esperaba|espera|esperaria|deberia|debia)\s+(?:de\s+)?(?:que\s+)?"
    r"|(?:el\s+sistema|la\s+aplicacion|el\s+aplicativo|el\s+modulo|la\s+pantalla"
    r"|la\s+funcionalidad|el\s+proceso|la\s+opcion|el\s+reporte|el\s+formulario"
    r"|la\s+pagina|la\s+accion|todo|esto|ello)\s+"
    r"|(?:que|y|pero|sin\s+embargo|en\s+su\s+lugar|en\s+cambio)\s*,?\s*"
)
```

**Bias, stated explicitly**: the matcher is tuned to minimise **false positives** and accepts **false negatives**. Replacing a genuine analyst expectation with the "no se pudo determinar" notice destroys information the analyst actually spoke; missing one hallucinated filler leaves a low-value line the analyst can delete in the editable `text_area`. This asymmetry is the design rule for every future blocklist entry.

## Post-Processor — Interface and Algorithm

```python
# generar_descripcion.py
ENCABEZADO_RESULTADO = "## Resultado esperado vs. obtenido"
AVISO_RESULTADO_NO_CONFIABLE = (
    "Resultado esperado vs. obtenido: no se pudo determinar de forma confiable"
)

def es_relleno_generico(cuerpo: str) -> bool: ...      # pura, total; exportada para tests
def postprocesar_descripcion(texto: str) -> str: ...   # pura, total; nunca lanza
```

`postprocesar_descripcion` — line-based, never a whole-document regex, so every byte it does not target is preserved verbatim:

1. `if not isinstance(texto, str) or not texto.strip(): return texto or ""` — total, tolerates a `None` content from the SDK.
2. **Fence stripping**: if the stripped text's first line matches `^```[a-zA-Z]*$` **and** its last line is `^```$`, drop both lines. Only a fence wrapping the *whole* output; inner fences are left alone.
3. **Locate the section**: scan lines for one whose normalised, `:`-stripped form equals the normalised `ENCABEZADO_RESULTADO`. Not found → **return unchanged (no-op)**.
4. **Body** = lines after the heading up to the next line starting with `## ` (or EOF).
5. Body empty/whitespace-only → replace with the notice (a dangling heading is as unusable as filler).
6. Otherwise `es_relleno_generico(cuerpo)`; `False` → **return unchanged**.
7. `True` → replace the body lines with a single `AVISO_RESULTADO_NO_CONFIABLE` line, preserving the heading and one blank line before the next section.

`es_relleno_generico(cuerpo)`:

1. **Specificity short-circuit** → `False` (genuine) if the body contains any digit, backtick, or quoted run (`"…"`/`«…»`). Numbers, identifiers and quotes are transcript-specific by construction. False-positive insurance.
2. Split into fragments on `\n`, `.`, `;`, and list markers (`-`, `*`, `1.`). Drop empties.
3. For each fragment: normalise → strip `_ANDAMIO` prefixes iteratively → the residue must be **exactly** a member of `FRASES_GENERICAS` (or empty).
4. `True` only if **every** fragment is generic and there was at least one fragment.

Exact residue matching (not substring) is what makes a two-line body with one real sentence and one filler sentence count as **genuine** — the spec's "entirely filler" condition, enforced literally.

## `generar_descripcion.py` Changes

```python
from prompts import (
    ENTRADA_GENERADOR_DESCRIPCION,
    ENTRADA_GENERADOR_DESCRIPCION_CON_CONTEXTO,
    GENERADOR_DESCRIPCION_TICKET,
    GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO,
)
```

- All four inline prompt constants (plus `REGLAS_CONTEXTO`) are **deleted**; the branch in `generar_descripcion` selects the imported names instead. `MODELO`, `temperature=0.2`, `max_tokens=1024`, `ProveedorContexto`, `_crear_cliente`, `ErrorConfiguracion`, `ErrorGeneracion` and both existing seams are untouched.
- Last line becomes `return postprocesar_descripcion(respuesta.choices[0].message.content)`.
- The post-processor runs **outside** the `try/except` that maps SDK failures to `ErrorGeneracion`, so a bug in pure post-processing can never be reported as a Groq API failure.
- Module docstring updated: prompts now live in `prompts.py`; output is the locked template, not prose.

**Testability is preserved byte-for-byte.** `FakeGroq`'s canned `"Descripción generada de prueba"` has no fence and no `## Resultado esperado vs. obtenido` heading, so step 3 returns it unchanged and every existing assertion still holds. New tests drive the post-processor directly with crafted response strings — no client, no network, no key.

## Data Flow

Fase 2's sequence diagram already covers this call path end to end; Fase 3 adds one pure step at the tail and changes no participant, no branch and no failure mode. A second diagram would restate it, so a compact note is used instead — per `openspec/config.yaml` ("sequence diagrams for **complex** flows").

    transcripción ─→ buscar_contexto()  ──┬─ "" ──→ GENERADOR_DESCRIPCION_TICKET
                                          └─ ctx ─→ ..._CON_CONTEXTO  (+ reglas 13-18)
                                                          │
                                        Groq (temp 0.2, max_tokens 1024)
                                                          │
                                          respuesta cruda (plantilla Markdown)
                                                          │
                              postprocesar_descripcion()  │  pura, total
                                ├─ quita fence envolvente ┤
                                ├─ sin sección "Resultado" → sin cambios (no-op)
                                ├─ cuerpo genuino          → sin cambios
                                └─ cuerpo relleno/vacío    → AVISO_RESULTADO_NO_CONFIABLE
                                                          │
                                                    app.py st.text_area (editable)

## File Changes

| File | Action | Description |
|---|---|---|
| `prompts.py` | Create | `PLANTILLA_TICKET_JIRA`, `GENERADOR_DESCRIPCION_TICKET`, `REGLAS_CONTEXTO_MODULO`, `GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO`, `ENTRADA_GENERADOR_DESCRIPCION(_CON_CONTEXTO)`, each with an attribute docstring. |
| `generar_descripcion.py` | Modify | Delete inline prompts; import from `prompts`; add `ENCABEZADO_RESULTADO`, `AVISO_RESULTADO_NO_CONFIABLE`, `FRASES_GENERICAS`, `_ANDAMIO`, `es_relleno_generico`, `postprocesar_descripcion`; post-process the response before returning. |
| `tests/test_generar_descripcion.py` | Modify | Imports move to `prompts`; template/omission prompt assertions; post-processor unit tests; `CONTEXTO_SUBMODULO_SINTETICO`; `ast` no-inline-prompt scan. |
| `openspec/specs/jira-description-generation/spec.md` | Modify | Delta applied at archive time. |
| `README.md`, `CLAUDE.md` | Modify | Note the ticket template output and `prompts.py` (convention section already added). |
| `app.py`, `contexto_memoria.py`, `transcribir.py`, `memory/`, `requirements.txt` | Unchanged | `app.py` imports only `generar_descripcion` + the two error types; no prompt constant crosses that boundary. |

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit — prompt shape | Both system prompts contain `PLANTILLA_TICKET_JIRA` verbatim, the four headings in order, the absolute MUST NOT (rule 5), the omission rule (rules 3–4), the `Módulo afectado: no identificado` literal (rule 6) and the no-fence/no-preamble rule (rule 12) | Assert against the imported constants; existing `FakeGroq` recorder for the wiring |
| Unit — prompt selection | No context → system message is exactly `GENERADOR_DESCRIPCION_TICKET`; context → exactly `..._CON_CONTEXTO`, `startswith` the base, contains rules 13–18 | Existing `proveedor_contexto` seam |
| Unit — sub-module | Context documenting `Matriz de riesgos` reaches the user message verbatim inside `===`, and the `Módulo > Submódulo` rule is present in the system message | `CONTEXTO_SUBMODULO_SINTETICO` + `lambda t: ...` |
| Unit — post-processor | Filler body → replaced with the notice, heading kept; genuine body → byte-identical; absent section → whole text byte-identical; empty body → notice; wrapping fence → stripped, inner fence kept; multi-fragment body with one real sentence → unchanged | Direct calls on crafted strings; table-driven over `FRASES_GENERICAS` and over a genuine-expectation counter-table |
| Unit — repository rule | `generar_descripcion.py` has no module-level `str` constant longer than ~120 chars | `ast.parse` on the source file |
| Unit — regression | Fase 1/2 assertions (rules 9/10 wording, `---`/`===` delimiters, `ErrorConfiguracion` fail-fast, byte-identical no-context request) still pass | Unchanged existing tests |
| Manual E2E | Real model emits the template, omits unstated sections, and names a sub-module | **Blocked** on `GROQ_API_KEY` — explicit follow-up |

## Threat Matrix

N/A — no routing, shell commands, subprocess spawning, VCS/PR automation, executable-file classification, or process integration. No new I/O boundary: `prompts.py` is data, the post-processor is a pure in-memory `str -> str`.

## Migration / Rollout

No migration, no schema, no deploy state. One new file plus one modified module; `git revert` of the single PR restores Fase 2 prose output byte-for-byte. Partial rollback without a revert: drop the `postprocesar_descripcion(...)` wrapper on the return statement — prompt-only behaviour (exploration Approach 1) remains intact.

## Open Questions

- [ ] `GROQ_API_KEY` unprovisioned: template compliance, per-section omission and sub-module naming are verified as *prompt content*, never as *model behaviour*. Manual smoke test is a required follow-up before this is trusted in front of analysts.
- [ ] Blocklist coverage is a first pass over predicted phrasings, not observed ones. Once real outputs exist, entries should be added from actual model text — keeping the false-positive-averse bias.
- [ ] Whether the real Kawak `memory/` documents sub-modules at all is unconfirmed; rule 14 is harmless if it never fires, but the `Módulo > Submódulo` format should be confirmed with the owning team before analysts rely on it.
