# Design: Retire Groq, run all LLM processing on Claude Haiku 4.5

Mirror: Engram `sdd/migracion-groq-a-haiku/design`.
Depends on: `proposal.md` (decisions 1-7, all resolved) and `explore.md` (call-site map).

> **Addendum (second pass).** The spec phase added a whole new capability,
> `specs/qa-documentacion/spec.md`, after this design's first pass was written. Decisions
> **15-18** below, the `consultar_documentacion.py` / `prompts.py` / `app.py` sections, and
> the `tests/test_consultar_documentacion.py` section were extended for it. Everything else
> is unchanged from the first pass.
>
> **Proposal record is stale — do not plan from it.** `proposal.md` still says
> *"### New Capabilities — None."* That is no longer true: `qa-documentacion` is a **new**
> capability with 5 ADDED requirements and 8 scenarios, and it changes the `responder_consulta`
> return contract. `sdd-tasks` MUST plan from this design plus
> `specs/qa-documentacion/spec.md`, not from the proposal's Capabilities or Affected-Areas
> tables (the latter also predates the `app.py` UI branching). Reconciling `proposal.md` is
> the orchestrator's call, not this design's edit.

> Size note: this document exceeds the generic 800-word SDD design budget on purpose.
> Every prior design in `openspec/changes/archive/` ships exact module contents and exact
> diffs (see `2026-09-02-enriquecimiento-documentacion-haiku/design.md`); the project
> convention wins per `openspec/config.yaml` `rules.design` and CLAUDE.md.

## Technical Approach

Proposal Approach 2 with the rename included. `contexto_enriquecido.py` is renamed to
`cliente_anthropic.py` and slimmed to provider scaffolding only. Every one of the four LLM
call sites imports that one module and calls `claude-haiku-4-5-20251001`. The enrichment
step, its content-addressed cache, and its two prompts are deleted; `buscar_contexto()`
assembles verbatim raw `.md` content for the (still max 3) selected documents under a
120,000-character budget. The `groq` dependency and every Groq-shaped helper disappear.

Three provider differences drive the whole diff and nothing else does:

| Groq (OpenAI-compatible) | Anthropic Messages API |
|---|---|
| `cliente.chat.completions.create(...)` | `cliente.messages.create(...)` |
| `messages=[{"role":"system",...},{"role":"user",...}]` | `system="..."` (top level) + `messages=[{"role":"user",...}]` |
| `respuesta.choices[0].message.content` (str) | `respuesta.content` (list of blocks with `.type`/`.text`) |
| `response_format={"type":"json_object"}` | **no equivalent parameter** — see Decision 4 |
| `reasoning_effort="low"` (gpt-oss reasoning-token workaround) | **no equivalent and not needed** — extended thinking is off by default on Haiku 4.5 |
| error text carries `"try again in Xs"` | no parseable wait text — fixed backoff |

## Architecture Decisions

| # | Decision | Choice | Rejected alternative | Rationale |
|---|---|---|---|---|
| 1 | Shared module | Rename `contexto_enriquecido.py` → `cliente_anthropic.py`, slimmed to `ErrorConfiguracion`, `_crear_cliente`, `_crear_mensaje_con_reintento`, `_texto_de`, `_pedir_json`, `MODELO_HAIKU` | New file + delete the old one | Same net result with `git mv`-shaped history; only 3 importers + Dockerfile to repoint. The existing `_crear_cliente`/`_crear_mensaje_con_reintento` are already live-verified against `anthropic` 1.3.0 |
| 2 | Missing-key error type | ONE `ErrorConfiguracion` in `cliente_anthropic`; fatality is a call-site policy | Keep two types (`ErrorConfiguracion` fatal + `ErrorConfiguracionAnthropic` non-fatal) | Proposal decision 1. Two exception types for one condition was the actual defect. Generation/Q&A let it propagate (fail-fast preserved); `buscar_contexto`'s outer `except Exception` and the verifier's `try` catch it and degrade — the contracts are unchanged, only the class count is |
| 3 | `ErrorGeneracion` location | Stays in `generar_descripcion.py`, message reworded Groq → Anthropic | Move to `cliente_anthropic` | It is a *generation-failed* domain error, not provider scaffolding; `consultar_documentacion` and `app.py` already import it from there. Moving it would churn 4 files for zero gain |
| 4 | JSON responses (selector + verifier) | `_pedir_json()`: assistant **prefill** with `{`, then `json.JSONDecoder().raw_decode("{" + texto)` | (a) tool-use with `tool_choice={"type":"tool",...}`; (b) plain `json.loads` on a free-form answer | The Messages API has NO `response_format`. Prefill is the documented no-schema equivalent and it makes a code fence or a preamble structurally impossible (the turn is already inside a JSON object). Tool-use was rejected because it would force every fake in the suite to grow `tool_use` content blocks, discarding the reusable `FakeAnthropic` shape. `raw_decode` (not `loads`) tolerates trailing prose after the object — a bare `loads` failure in the selector costs the user all context |
| 5 | `_texto_de()` + `_pedir_json()` live in the shared module | Yes — two small pure helpers beyond the literal slim list | Duplicate block-extraction in 4 modules and the prefill trick in 2 | `_texto_de` is needed by all four call sites (the response shape changed for everyone); `_pedir_json` is needed by two. Both are provider scaffolding, not domain logic. Reversible: inlining them later touches only `cliente_anthropic.py` and its importers |
| 6 | Model ids | `MODELO_HAIKU = "claude-haiku-4-5-20251001"` defined once; `MODELO`, `MODELO_AUXILIAR`, `MODELO_SELECTOR` all alias it | Keep three distinct ids / delete the aliases | **Confirmed: there is no larger or smaller Haiku 4.5 tier** — one id serves generation, selection and verification. Aliases are retained because `modelo=` is a public kwarg on two functions and tests assert `kwargs["model"]`, so deleting them would be a gratuitous API break; the single source makes "one model everywhere" structural |
| 7 | Client sharing | `generar_descripcion()` builds the client first, then wraps `buscar_contexto` in a 1-arg closure that threads it. `responder_consulta()` threads only an already-injected client | Hoist client creation above context retrieval in Q&A too | Proposal decision 2. In Q&A, hoisting would make "no key + no matching docs" raise instead of returning `SIN_INFORMACION`, and would break `test_no_context_returns_fixed_notice_without_any_network_call`. Building one extra client object (no network, no auth) is the cheaper trade |
| 8 | `proveedor_contexto` seam | Unchanged `Callable[[str], str]`; the client is bound by closure | Widen the type to accept `cliente` | Keeps every injected test double a plain 1-arg lambda; zero churn in the seam's 8 existing usages |
| 9 | Verifier | Stays a separate conditional pass | Merge into generation via structured output | Proposal decision 5. Self-grading text you just wrote regresses a product guarantee; the speed win comes from deleting N enrichment calls per request instead |
| 10 | Raw block format | Verbatim content, joined by `\n\n`, no path header | Prefix each block with `## <ruta>` | Proposal says "verbatim raw content"; `_ensamblar_contexto` then needs no change at all. Path headers are a real grounding improvement but a separate tuning decision — see Open Questions |
| 11 | `PRESUPUESTO_CARACTERES` | `120_000` | Token-aware budgeting | Proposal decision (confirmed): ~30K tokens, 15% of the window; 3 docs × ~40KB before truncation, so real Kawak per-screen docs pass whole. Character truncation stays a deterministic safety valve; a tokenizer dependency buys nothing at this margin |
| 12 | `CARACTERES_POR_LOTE` | Unchanged at `12000` | Raise it now that Groq's 8000 TPM cap is gone | Batching is no longer only a TPM workaround: the per-batch scan + cross-batch re-rank is a *quality* mechanism with a live-found regression test behind it (`aud_auditoria` beating `gst_documental`). Changing batch size in the same PR that changes providers would make a selection-quality regression unattributable |
| 13 | Prompt text | No wording changes; only the two `ENRIQUECEDOR_*` constants are deleted + 3 docstrings corrected | Rewrite prompts for Haiku's style | Verified against the current text: every Groq-specific assumption lives in **code** (`response_format`, `reasoning_effort`), not in prompt text. The JSON prompts' `{"archivos": [...]}` / `{"fundamentado": true}` examples stay exactly correct under prefill |
| 14 | Cache removal | Delete `cache/documentacion/` usage and the docker-compose volume; leave `cache/` in `.gitignore`/`.dockerignore` | Also remove the ignore entries | The volume would recreate an empty bind-mount dir on every `up`; the ignore entries cost nothing and still protect a stale local `cache/` from being committed |
| **15** | **Q&A return contract** (3 states) | `responder_consulta()` returns a frozen dataclass `RespuestaConsulta(texto: str, tipo: Literal[...])`, with the three `TIPO_*` values as module constants next to `SIN_INFORMACION` | (a) sentinel prefix on the existing `str`; (b) `NamedTuple`; (c) raise a `PreguntaAclaratoria` exception; (d) keep `str` + a second out-param | Three states cannot ride one `str`: the clarifying-question text is model-generated, so no comparable sentinel exists (unlike the fixed `SIN_INFORMACION`). A prefix leaks into `st.text_area` the moment a parse slips. `NamedTuple` rejected because `RespuestaConsulta(t, "respuesta") == (t, "respuesta")` is True — tuple-equality invites both index access and accidentally-passing assertions. Exceptions rejected: a clarifying question is a normal successful outcome, not an error. The `TIPO_*` string constants deliberately mirror the existing `SIN_INFORMACION` module-constant idiom rather than introducing an `Enum` (the codebase has zero `Enum`/`dataclass`/`NamedTuple` usage today — one new construct, not three) |
| **16** | **Wire format** for answer-vs-question | **Assistant prefill of a type tag**: prefill `"[TIPO:"`, model completes `RESPUESTA]` or `ACLARACION]`, parser re-prepends the prefill and `partition("]")` on the result | (a) `_pedir_json` with `{"tipo": ..., "texto": ...}`; (b) free-form text searched for a marker | Reuses Decision 4's own idiom (prefill makes a preamble structurally impossible) without JSON's fatal flaw *here*: the Q&A payload is up to 1024 tokens of multi-paragraph Spanish prose, and a single unescaped newline inside a JSON string destroys **the entire answer the analyst waited for**. The tag carries no payload, so a malformed tag can only mislabel, never delete. Option (b) rejected exactly as the brief says — a *searched* marker can match text the model wrote mid-answer; this marker is **anchored at index 0 and built from bytes we sent**, so it cannot be confused with model prose |
| **17** | Parse-failure policy | Unknown/absent tag → `TIPO_RESPUESTA` with the **full raw text** kept verbatim | Raise, or return `SIN_INFORMACION` | Same precedent as `_verificar_resultado_esperado`'s "any failure → keep the analyst's text" and `buscar_contexto`'s never-raise: a parser slip must never destroy real content or silently degrade into the reserved no-information state (which the spec forbids collapsing) |
| **18** | Prompt scope | Decision 13's "no prompt wording changes" is **scoped to the migration**; `RESPONDEDOR_CONSULTA_DOCUMENTACION` is rewritten because `qa-documentacion` is new behavior, not a provider difference | Ship the migration first and the Q&A prompt in a follow-up change | The spec is ADDED in *this* change's delta; shipping the delta without the prompt would land requirements nothing satisfies. Contained to one constant plus three new ones — all other prompts still obey Decision 13 |

## Data Flow

Before (2 providers, 4 + N round trips):

    buscar_contexto ─ Groq selector ─ read raw ─ Anthropic enrich ×N (cache) ─ assemble(6 000)
                                                                                     │
    generar_descripcion ── Groq gpt-oss-120b ── postprocesar ── Groq gpt-oss-20b verifier

After (1 provider, 2-3 round trips):

    generar_descripcion(transcripcion)
      │
      ├─ cliente = _crear_cliente()            ← ONE client, fail-fast on missing key
      │
      ├─ buscar_contexto(transcripcion, cliente=cliente)          contexto_memoria.py
      │     ├─ listar_documentos()                    (preview listing, never enriched)
      │     ├─ elegir_documentos_relevantes(cliente)  Haiku 4.5, _pedir_json, ≤3 paths
      │     │     └─ _preguntar_selector per batch (12 000 chars) + cross-batch re-rank
      │     ├─ read_text() per selected path ──→ [contenido_raw, ...]  selection order
      │     └─ _ensamblar_contexto(bloques, 120 000)   ← verbatim, deterministic truncation
      │           (ANY exception above ──→ "" ; NEVER raises)
      │
      ├─ messages.create(system=GENERADOR_..., model=MODELO)      Haiku 4.5, 1024 out
      │     └─ failure ──→ ErrorGeneracion (fatal, surfaced by app.py)
      │
      └─ postprocesar_descripcion(_texto_de(respuesta), transcripcion, cliente)
            └─ only if "## Resultado esperado vs. obtenido" present:
                 _verificar_resultado_esperado ── _pedir_json(cliente, MODELO_AUXILIAR)
                       └─ ANY failure ──→ True (keep the analyst's text)

Q&A path (`consultar_documentacion.responder_consulta`) keeps its current ordering —
context first, client second — so a question with no matching docs still short-circuits
without a key. It now resolves to one of three typed states:

    responder_consulta(pregunta)
      │
      ├─ contexto = proveedor_contexto(pregunta)      ← same buscar_contexto pipeline
      │     └─ "" ──→ RespuestaConsulta(SIN_INFORMACION, TIPO_SIN_INFORMACION)
      │               ZERO network calls, no client built  (spec: degrade stays distinct)
      │
      ├─ cliente = _crear_cliente()                   ← only now; ErrorConfiguracion is fatal here
      │
      ├─ messages.create(system=RESPONDEDOR_CONSULTA_DOCUMENTACION,
      │                  messages=[user, {"role":"assistant","content":"[TIPO:"}])
      │     └─ failure ──→ ErrorGeneracion (fatal, surfaced by app.py)
      │
      └─ _interpretar_respuesta("[TIPO:" + _texto_de(respuesta))
            ├─ "[TIPO:ACLARACION]…"  ──→ RespuestaConsulta(pregunta_al_analista, TIPO_PREGUNTA_ACLARATORIA)
            ├─ "[TIPO:RESPUESTA]…"   ──→ RespuestaConsulta(respuesta, TIPO_RESPUESTA)
            └─ anything else         ──→ RespuestaConsulta(texto_crudo, TIPO_RESPUESTA)   ← never loses text

Uncertainty/variability is **not** a fourth state: per the spec it is prose *inside* a
`TIPO_RESPUESTA` answer (a network call was made and context was found), which is exactly
what keeps it distinguishable from `TIPO_SIN_INFORMACION` (no call, no context, fixed text).

## File Changes

| File | Action | Description |
|---|---|---|
| `contexto_enriquecido.py` → `cliente_anthropic.py` | Rename + rewrite | Slimmed to client / retry / `_texto_de` / `_pedir_json` / `ErrorConfiguracion` / `MODELO_HAIKU`. Deleted: `enriquecer_documentos`, `_enriquecer_uno`, `ErrorEnriquecimiento`, `resolver_directorio_cache`, `_hash_contenido`, `_leer_cache`, `_escribir_cache`, `MODELO_ENRIQUECEDOR`, `MAX_TOKENS_ENRIQUECIMIENTO`, `MAX_TRABAJADORES`, `DIRECTORIO_CACHE_POR_DEFECTO`, `ErrorConfiguracionAnthropic` |
| `generar_descripcion.py` | Modify | Drop `_crear_cliente`, `_crear_completion_con_reintento`, `ErrorConfiguracion`, `_PATRON_ESPERA_RATE_LIMIT`, `MAX_REINTENTOS_RATE_LIMIT`, `import json/os/time`. Repoint `generar_descripcion()` + `_verificar_resultado_esperado()`. Thread the client into the default context provider |
| `contexto_memoria.py` | Modify | Haiku selector via `_pedir_json`; enrichment step + `Enriquecedor` alias + `enriquecedor=` kwarg removed; `PRESUPUESTO_CARACTERES = 120_000`; lazy Groq import replaced by a module-level `cliente_anthropic` import (the old import cycle is gone) |
| `consultar_documentacion.py` | Modify | Imports from `cliente_anthropic`; `system=`/`_texto_de`; error message reworded. **Plus (`qa-documentacion`): new `RespuestaConsulta` frozen dataclass + `TIPO_RESPUESTA`/`TIPO_PREGUNTA_ACLARATORIA`/`TIPO_SIN_INFORMACION` constants; new `_interpretar_respuesta()`; the call now sends an assistant prefill; return type `str` → `RespuestaConsulta` (breaking, 1 production caller)** |
| `prompts.py` | Modify | Delete `ENRIQUECEDOR_DOCUMENTACION` + `ENTRADA_ENRIQUECEDOR_DOCUMENTACION`; correct 3 docstrings that name Groq. **Plus (`qa-documentacion`): rewrite `RESPONDEDOR_CONSULTA_DOCUMENTACION`; add `PREFILL_RESPONDEDOR_CONSULTA`, `MARCA_RESPUESTA_DIRECTA`, `MARCA_PREGUNTA_ACLARATORIA`. `ENTRADA_RESPONDEDOR_CONSULTA` unchanged** |
| `app.py` | Modify | Import `ErrorConfiguracion` from `cliente_anthropic` (3-line import block change). **Plus (`qa-documentacion`): unwrap `RespuestaConsulta` into the existing `st.session_state.resultado` string, add `st.session_state.tipo_respuesta`, and branch the result card's title/subtitle on it.** **Addition to the proposal's affected-areas list** |
| `requirements.txt` | Modify | Drop `groq>=0.11` |
| `Dockerfile` | Modify | `contexto_enriquecido.py` → `cliente_anthropic.py` in the `COPY` list |
| `docker-compose.yml` | Modify | Remove the `./cache/documentacion` volume |
| `tests/test_contexto_enriquecido.py` → `tests/test_cliente_anthropic.py` | Rename + rewrite | Keeps the `FakeAnthropic` family verbatim as the reference double; all 11 enrichment/cache tests deleted; scaffolding tests added |
| `tests/test_generar_descripcion.py` | Modify | `FakeGroq` → `FakeAnthropic`; 4 retry tests move out; `response_format` assertion replaced |
| `tests/test_contexto_memoria.py` | Modify | `FakeGroq*` → `FakeAnthropic*`; 3 enrichment tests deleted, 4 raw-content/budget tests added |
| `tests/test_consultar_documentacion.py` | Modify | `FakeGroq` → `FakeAnthropic`; SDK monkeypatch retargeted. **Plus (`qa-documentacion`): every assertion moves from a bare string to `.texto`/`.tipo`; 8 tests added for the three states, the prefill, the parse-failure degrade and the prompt shape** |
| `openspec/specs/*` (**4** specs) | Modify/Add | Delta passes per the Capabilities section (sdd-spec owns these, not this design). **`qa-documentacion` is an ADDED capability, not in the proposal's list of 3** |

Not touched: `transcribir.py`, `logging_config.py`, `tests/test_transcribir.py`, `.gitignore`,
`.dockerignore`. No `.env*` file is tracked in this repo, so the `GROQ_API_KEY` →
`ANTHROPIC_API_KEY` swap is an operator step, not a file edit.

## Interfaces / Contracts

### `cliente_anthropic.py` — complete final contents

```python
"""Shared Anthropic (Claude Haiku 4.5) scaffolding for every LLM call in this project.

Owns the client lifecycle, the Anthropic 429 retry wrapper, text-block
extraction, and the JSON-response helper that stands in for Groq's
`response_format={"type": "json_object"}` — the Messages API has no such
parameter (see `_pedir_json`).

Renamed from `contexto_enriquecido.py`: the summarization step, its
content-addressed cache under `cache/documentacion/`, and the `ENRIQUECEDOR_*`
prompts were deleted when verbatim raw-document injection replaced enrichment
(openspec change `migracion-groq-a-haiku`).

`ErrorConfiguracion` is the ONE missing-key error for the whole project.
Whether it is fatal is a CALL-SITE policy, not a property of the exception:
`generar_descripcion` and `consultar_documentacion` let it propagate to the UI
(fail-fast); `contexto_memoria.buscar_contexto` and
`generar_descripcion._verificar_resultado_esperado` catch it and degrade.

Never imports Streamlit. Never logs the key value.
"""

from __future__ import annotations

import json
import logging
import os
import time

logger = logging.getLogger(__name__)

# The only model id in the project. Claude Haiku 4.5 has no larger/smaller
# tier, so selection, generation and verification all use this one.
MODELO_HAIKU = "claude-haiku-4-5-20251001"

MAX_REINTENTOS_RATE_LIMIT = 3
# Anthropic's error text has no Groq-style "try again in Xs" to parse, and the
# `retry-after` header was not live-verified — fixed backoff on purpose.
ESPERA_RATE_LIMIT = 5.0


class ErrorConfiguracion(RuntimeError):
    """ANTHROPIC_API_KEY absent/blank — raised before any HTTP call."""


def _crear_cliente():
    """Build the Anthropic client, failing fast if the API key is not set.

    Reads ANTHROPIC_API_KEY only from the environment. Never logs its value.
    """
    clave = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not clave:
        logger.warning("ANTHROPIC_API_KEY ausente o vacía al intentar llamar a Haiku.")
        raise ErrorConfiguracion(
            "ANTHROPIC_API_KEY no está configurada. Debe definirse la variable de "
            "entorno (ver .env.example) antes de generar una descripción."
        )

    from anthropic import Anthropic

    return Anthropic(api_key=clave)


def _crear_mensaje_con_reintento(cliente, **kwargs):
    """`cliente.messages.create(**kwargs)` with 429 retry.

    `status_code == 429` verified live against anthropic 1.3.0. Shared by every
    call site in this project — import from here, never duplicate.
    """
    intentos = 0
    while True:
        try:
            return cliente.messages.create(**kwargs)
        except Exception as exc:
            es_rate_limit = getattr(exc, "status_code", None) == 429
            intentos += 1
            if not es_rate_limit or intentos > MAX_REINTENTOS_RATE_LIMIT:
                raise
            logger.warning(
                "Rate limit de Anthropic alcanzado, reintentando en %.1fs (intento %d/%d)",
                ESPERA_RATE_LIMIT, intentos, MAX_REINTENTOS_RATE_LIMIT,
            )
            time.sleep(ESPERA_RATE_LIMIT)


def _texto_de(respuesta) -> str:
    """Concatenate the `text` blocks of an Anthropic response.

    Anthropic returns a LIST of content blocks, not Groq's
    `choices[0].message.content`. Every call site goes through this, and every
    `FakeAnthropic` in the test suite mimics exactly this shape.
    """
    return "".join(
        bloque.text
        for bloque in respuesta.content
        if getattr(bloque, "type", None) == "text"
    ).strip()


def _pedir_json(cliente, *, model: str, system: str, mensaje_usuario: str, max_tokens: int) -> dict:
    """JSON-only call. Stands in for Groq's `response_format={"type":"json_object"}`.

    The Anthropic Messages API has NO `response_format` parameter. The
    documented schema-free equivalent is ASSISTANT PREFILL: seed the assistant
    turn with `{` so the model can only continue a JSON object — which also
    makes a code fence or a preamble structurally impossible. `raw_decode`
    (not `loads`) parses the first object and ignores any trailing prose.

    Raises on an unparseable answer; each caller decides how to degrade.
    """
    respuesta = _crear_mensaje_con_reintento(
        cliente,
        model=model,
        max_tokens=max_tokens,
        temperature=0.0,
        system=system,
        messages=[
            {"role": "user", "content": mensaje_usuario},
            {"role": "assistant", "content": "{"},  # prefill — no trailing whitespace allowed
        ],
    )
    datos, _ = json.JSONDecoder().raw_decode("{" + _texto_de(respuesta))
    return datos
```

### `generar_descripcion.py` — exact edits

Docstring: replace every "Groq" with "Haiku"/"Anthropic"; replace the
`GROQ_API_KEY` sentence with `ANTHROPIC_API_KEY`; note that the client is now built once
per request and threaded into retrieval and verification.

Imports and constants (replaces current lines 32-56 and 70-130):

```python
from __future__ import annotations

import logging
import re
from typing import Callable, Optional

from cliente_anthropic import (
    MODELO_HAIKU,
    _crear_cliente,
    _crear_mensaje_con_reintento,
    _pedir_json,
    _texto_de,
)
from prompts import (
    ENTRADA_GENERADOR_DESCRIPCION,
    ENTRADA_GENERADOR_DESCRIPCION_CON_CONTEXTO,
    GENERADOR_DESCRIPCION_TICKET,
    GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO,
)

logger = logging.getLogger(__name__)

MODELO = MODELO_HAIKU
# Nominal only: Claude Haiku 4.5 has no cheaper tier, so the verifier runs on
# the same model. Kept as a named constant because it is the `model` value the
# verifier call sends and the tests assert on.
MODELO_AUXILIAR = MODELO_HAIKU

ProveedorContexto = Callable[[str], str]


class ErrorGeneracion(RuntimeError):
    """Raised on Anthropic SDK auth/API failures. Never includes the key value."""
```

Deleted outright: `import json`, `import os`, `import time`, `_PATRON_ESPERA_RATE_LIMIT`,
`MAX_REINTENTOS_RATE_LIMIT`, `_crear_completion_con_reintento`, `class ErrorConfiguracion`,
`def _crear_cliente`. `ENCABEZADO_RESULTADO`, `AVISO_RESULTADO_NO_CONFIABLE`,
`_PATRON_FENCE_INICIO`, `_PATRON_FENCE_FIN` and all of `postprocesar_descripcion` are
unchanged.

`_verificar_resultado_esperado` (replaces current lines 135-173):

```python
def _verificar_resultado_esperado(transcripcion: str, cuerpo: str, cliente) -> bool:
    """Ask Haiku whether `cuerpo` is explicitly grounded in `transcripcion`,
    or an invented/generic expectation nobody stated.

    Defaults to True (assume grounded, keep the text) on any failure — a broken
    verifier must never silently erase real analyst-provided content. This is
    also the call site that treats `ErrorConfiguracion` as NON-fatal. Never raises.
    """
    from prompts import (
        ENTRADA_VERIFICADOR_RESULTADO_ESPERADO,
        VERIFICADOR_RESULTADO_ESPERADO,
    )

    try:
        datos = _pedir_json(
            cliente,
            model=MODELO_AUXILIAR,
            system=VERIFICADOR_RESULTADO_ESPERADO,
            mensaje_usuario=ENTRADA_VERIFICADOR_RESULTADO_ESPERADO.format(
                transcripcion=transcripcion, cuerpo=cuerpo
            ),
            max_tokens=150,
        )
        return bool(datos.get("fundamentado", True))
    except Exception as exc:
        logger.warning(
            "Verificación de 'Resultado esperado' falló, se conserva el texto: %s: %s",
            type(exc).__name__, exc,
        )
        return True
```

`generar_descripcion` (replaces current lines 253-291; signature unchanged):

```python
    if cliente is None:
        cliente = _crear_cliente()

    if proveedor_contexto is None:
        from contexto_memoria import buscar_contexto

        # One client per top-level request: the SAME Haiku client serves
        # selection, generation and verification (proposal decision 2). An
        # injected `proveedor_contexto` keeps its plain 1-arg contract.
        def proveedor_contexto(texto: str) -> str:
            return buscar_contexto(texto, cliente=cliente)

    contexto = proveedor_contexto(transcripcion)

    if contexto:
        system_prompt = GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO
        mensaje_usuario = ENTRADA_GENERADOR_DESCRIPCION_CON_CONTEXTO.format(
            contexto=contexto, transcripcion=transcripcion
        )
    else:
        system_prompt = GENERADOR_DESCRIPCION_TICKET
        mensaje_usuario = ENTRADA_GENERADOR_DESCRIPCION.format(transcripcion=transcripcion)

    try:
        respuesta = _crear_mensaje_con_reintento(
            cliente,
            model=modelo,
            max_tokens=1024,
            temperature=0.2,
            system=system_prompt,
            messages=[{"role": "user", "content": mensaje_usuario}],
        )
    except Exception as exc:
        logger.error(
            "Fallo en la llamada a Haiku (modelo=%s): %s: %s",
            modelo, type(exc).__name__, exc,
        )
        raise ErrorGeneracion(
            "No se pudo generar la descripción (fallo de autenticación o de "
            "la API de Anthropic). Ver logs/app.log para el detalle técnico."
        ) from exc

    return postprocesar_descripcion(_texto_de(respuesta), transcripcion, cliente)
```

### `contexto_memoria.py` — exact edits

Docstring: replace "Groq itself picks which files" with "Haiku itself picks which files";
delete the whole final paragraph about `contexto_enriquecido.enriquecer_documentos` and
replace it with:

```
The verbatim raw content of the finally-selected documents is injected as
context — there is no summarization step. Haiku 4.5's 200K window makes
compression unnecessary; `PRESUPUESTO_CARACTERES` is a truncation safety
valve, not the normal path.
```

Imports and constants (replaces current lines 27-52):

```python
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable, Optional

from cliente_anthropic import MODELO_HAIKU, _crear_cliente, _pedir_json

logger = logging.getLogger(__name__)

# ~30K tokens, 15% of Haiku 4.5's window. At most 3 selected documents means
# ~40KB each before truncation, so real per-screen Kawak docs pass whole.
PRESUPUESTO_CARACTERES = 120_000
MARCADOR_TRUNCADO = "[contenido truncado]"

MAX_DOCUMENTOS_LISTADOS = 500  # safety valve on listing size, not a schema requirement
MAX_ARCHIVOS_SELECCIONADOS = 3
LONGITUD_VISTA_PREVIA = 160

MODELO_SELECTOR = MODELO_HAIKU

ProveedorContexto = Callable[[str], str]
```

Deleted: `import json` (now inside `_pedir_json`), the `gpt-oss` reasoning-token comment
block above `MODELO_SELECTOR`, and `Enriquecedor = Callable[...]`.

`CARACTERES_POR_LOTE` comment (replaces current lines 221-226):

```python
# The listing is chunked so selection scales to a corpus of any size. This
# began as a workaround for Groq's 8000 TPM free-tier cap (a real 273-file
# listing needed ~14000), but it is kept under Haiku as a QUALITY mechanism:
# every batch is scanned in isolation and re-ranked, which is what fixed the
# live `aud_auditoria` vs `gst_documental` false positive. Retuning this value
# belongs to a separate change, not the provider migration.
CARACTERES_POR_LOTE = 12000
```

`_preguntar_selector` (replaces current lines 252-276):

```python
def _preguntar_selector(transcripcion: str, documentos: list[tuple[str, str]], cliente) -> list[str]:
    """One Haiku call over a single (already budget-sized) document listing."""
    from prompts import ENTRADA_SELECTOR_DOCUMENTOS, SELECTOR_DOCUMENTOS_RELEVANTES

    datos = _pedir_json(
        cliente,
        model=MODELO_SELECTOR,
        system=SELECTOR_DOCUMENTOS_RELEVANTES,
        mensaje_usuario=ENTRADA_SELECTOR_DOCUMENTOS.format(
            transcripcion=transcripcion,
            listado=_construir_listado(documentos),
        ),
        max_tokens=500,
    )
    return datos.get("archivos", [])
```

`elegir_documentos_relevantes` is unchanged except for "Ask Groq" → "Ask Haiku" in its
docstring.

`buscar_contexto` (replaces current lines 320-391 in full):

```python
def buscar_contexto(
    transcripcion: str,
    *,
    directorio: Optional[str] = None,
    cliente=None,
) -> str:
    """Total provider: returns bounded raw document context, or `""`. Never raises.

    `cliente` is injected for testing AND for client sharing: `generar_descripcion`
    passes the same Haiku client it uses for generation and verification. When
    None, `cliente_anthropic._crear_cliente()` is called here; a missing
    `ANTHROPIC_API_KEY` raises `ErrorConfiguracion`, which the outer `except`
    below turns into `""`. This module NEVER propagates a configuration error —
    fatality is the caller's policy, not this function's.

    The verbatim raw content of each selected document is injected in selection
    order; `_ensamblar_contexto` truncates only if the total exceeds
    `PRESUPUESTO_CARACTERES`.
    """
    try:
        documentos = listar_documentos(directorio)
        if not documentos:
            return ""

        if cliente is None:
            cliente = _crear_cliente()

        seleccionados = elegir_documentos_relevantes(transcripcion, documentos, cliente)
        if not seleccionados:
            return ""

        raiz = resolver_directorio(directorio)
        bloques: list[str] = []
        for ruta_relativa in seleccionados:
            try:
                contenido = (raiz / ruta_relativa).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            bloques.append(contenido)

        if not bloques:
            return ""

        return _ensamblar_contexto(bloques, PRESUPUESTO_CARACTERES)
    except Exception as exc:
        logger.warning(
            "buscar_contexto degradó a sin-contexto (directorio=%s): %s: %s",
            directorio, type(exc).__name__, exc,
        )
        return ""
```

`_ensamblar_contexto`, `_truncar_bloque`, `listar_documentos`, `nombres_conocidos`,
`diagnosticar`, `resolver_directorio`, `_verificar_directorio`, `_resolver_seguro`,
`_vista_previa`, `_construir_listado`, `_lotes_de_documentos`: **unchanged**.

### `consultar_documentacion.py` — exact edits

Imports, constants and the new return type (replaces current lines 14-28):

```python
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Literal, Optional

from cliente_anthropic import (
    MODELO_HAIKU,
    _crear_cliente,
    _crear_mensaje_con_reintento,
    _texto_de,
)
from generar_descripcion import ErrorGeneracion
from prompts import (
    ENTRADA_RESPONDEDOR_CONSULTA,
    MARCA_PREGUNTA_ACLARATORIA,
    MARCA_RESPUESTA_DIRECTA,
    PREFILL_RESPONDEDOR_CONSULTA,
    RESPONDEDOR_CONSULTA_DOCUMENTACION,
)

logger = logging.getLogger(__name__)

MODELO = MODELO_HAIKU

SIN_INFORMACION = "No se encontró información sobre esto en la documentación disponible."

# The three states `responder_consulta` can resolve to. Plain module constants
# on purpose: same idiom as SIN_INFORMACION above, and the codebase has no
# Enum anywhere. `app.py` compares against these, never against raw literals.
TIPO_RESPUESTA = "respuesta"
TIPO_PREGUNTA_ACLARATORIA = "pregunta_aclaratoria"
TIPO_SIN_INFORMACION = "sin_informacion"

TipoRespuesta = Literal["respuesta", "pregunta_aclaratoria", "sin_informacion"]


@dataclass(frozen=True)
class RespuestaConsulta:
    """What the Q&A mode produced, and which of the three states it is.

    `texto` is ALWAYS the analyst-facing string — the answer, the clarifying
    question, or the fixed SIN_INFORMACION notice — so a caller that only
    renders `.texto` degrades to today's behavior. `tipo` exists because the
    three states are not distinguishable by inspecting the text: a clarifying
    question is model-generated prose with no fixed form.

    Frozen, and NOT a NamedTuple: tuple equality would make
    `RespuestaConsulta(t, TIPO_RESPUESTA) == (t, "respuesta")` silently true.
    """

    texto: str
    tipo: TipoRespuesta


ProveedorContexto = Callable[[str], str]
```

`_interpretar_respuesta` (new, private, pure — no network, trivially testable):

```python
def _interpretar_respuesta(texto_crudo: str) -> RespuestaConsulta:
    """Split the `[TIPO:...]` tag off the model's answer.

    The tag is STRUCTURAL, not searched for: `PREFILL_RESPONDEDOR_CONSULTA` is
    bytes WE sent as the assistant turn, so the type token can only be the very
    first thing in `texto_crudo`. That is what makes this different from a
    sentinel-prefix convention — a `]` the model wrote mid-answer produces an
    unrecognised tag, never a false positive.

    An unrecognised or absent tag degrades to a normal answer with the text
    kept VERBATIM. Same policy as `_verificar_resultado_esperado`: a parse slip
    must never destroy content the analyst waited for, and must never fall into
    the reserved SIN_INFORMACION state (the spec forbids collapsing the two).
    """
    marca, separador, cuerpo = texto_crudo.partition("]")
    if separador:
        marca = f"{marca.strip()}]"
        if marca == MARCA_PREGUNTA_ACLARATORIA:
            return RespuestaConsulta(cuerpo.strip(), TIPO_PREGUNTA_ACLARATORIA)
        if marca == MARCA_RESPUESTA_DIRECTA:
            return RespuestaConsulta(cuerpo.strip(), TIPO_RESPUESTA)
    logger.warning("Respuesta de consulta sin marca [TIPO:...] reconocible; se trata como respuesta directa.")
    return RespuestaConsulta(texto_crudo.strip(), TIPO_RESPUESTA)
```

Body of `responder_consulta` (replaces current lines 45-78; signature unchanged except
the return annotation `-> RespuestaConsulta`):

```python
    if proveedor_contexto is None:
        from contexto_memoria import buscar_contexto

        # `cliente` is still None here by design (see below), so retrieval
        # builds its own client for selection. When the caller DID inject one,
        # the closure shares it. Hoisting `_crear_cliente()` above this line
        # would make "no key + no matching docs" raise instead of returning
        # SIN_INFORMACION — that ordering is a product contract, not an accident.
        def proveedor_contexto(texto: str) -> str:
            return buscar_contexto(texto, cliente=cliente)

    contexto = proveedor_contexto(pregunta)
    if not contexto:
        return RespuestaConsulta(SIN_INFORMACION, TIPO_SIN_INFORMACION)

    if cliente is None:
        cliente = _crear_cliente()

    mensaje_usuario = ENTRADA_RESPONDEDOR_CONSULTA.format(contexto=contexto, pregunta=pregunta)

    try:
        respuesta = _crear_mensaje_con_reintento(
            cliente,
            model=modelo,
            max_tokens=1024,
            temperature=0.2,
            system=RESPONDEDOR_CONSULTA_DOCUMENTACION,
            messages=[
                {"role": "user", "content": mensaje_usuario},
                # Prefill: the answer can only START with the type tag. Same
                # trick as `_pedir_json`'s "{" — no trailing whitespace allowed.
                {"role": "assistant", "content": PREFILL_RESPONDEDOR_CONSULTA},
            ],
        )
    except Exception as exc:
        logger.error(
            "Fallo en la llamada a Haiku (modelo=%s): %s: %s",
            modelo, type(exc).__name__, exc,
        )
        raise ErrorGeneracion(
            "No se pudo responder la consulta (fallo de autenticación o de "
            "la API de Anthropic). Ver logs/app.log para el detalle técnico."
        ) from exc

    # The prefill is not echoed by the API, so re-prepend it before parsing —
    # exactly as `_pedir_json` does with its "{".
    return _interpretar_respuesta(PREFILL_RESPONDEDOR_CONSULTA + _texto_de(respuesta))
```

**Why not `_pedir_json` here.** `_pedir_json` is the project's one structured-output
helper and would have been the consistent choice, but its payload would be up to 1024
tokens of multi-paragraph Spanish prose inside a JSON string. One unescaped newline and
`raw_decode` throws away the whole answer. The tag carries no payload, so the same class
of model slip costs a label, not the answer (Decision 16).

Module docstring: "Reuses `generar_descripcion`'s Groq client construction (same
GROQ_API_KEY...)" → "Reuses `cliente_anthropic`'s shared Haiku client (same
`ANTHROPIC_API_KEY`, same fail-fast behavior)"; add a paragraph documenting the three
states and that `SIN_INFORMACION` is reserved for zero-retrieval only.

### `prompts.py` — exact edits

1. Module docstring: `"Every prompt sent to an LLM (Groq today, any future provider)"`
   → `"Every prompt sent to an LLM (Claude Haiku 4.5 today, any future provider)"`.
2. **Delete** `ENRIQUECEDOR_DOCUMENTACION` and its docstring (current lines 111-118).
3. **Delete** `ENTRADA_ENRIQUECEDOR_DOCUMENTACION` and its docstring (current lines 120-126).
4. **Rewrite `RESPONDEDOR_CONSULTA_DOCUMENTACION`** and add three protocol constants —
   see below (Decision 18). `ENTRADA_RESPONDEDOR_CONSULTA` is **unchanged**: the tag
   protocol lives in the system prompt and the prefill, so the user message stays a plain
   `contexto` + `pregunta` template.

**No other prompt text changes.** Verified against every constant: the Groq-specific
assumptions (`response_format`, `reasoning_effort`) live entirely in code. The JSON
examples `{"archivos": [...]}` and `{"fundamentado": true}` remain literally correct
under assistant prefill — the model is completing exactly that object. `.format()` is
only applied to the `ENTRADA_*` templates, none of which contain literal braces, so the
prefill change introduces no formatting hazard.

#### New: the Q&A type-tag protocol constants

Placed immediately above `RESPONDEDOR_CONSULTA_DOCUMENTACION`. They live in `prompts.py`,
not in `consultar_documentacion.py`, because they are literal prompt text — the same rule
that `test_no_inline_prompt_text_in_generar_descripcion` already enforces elsewhere.

```python
PREFILL_RESPONDEDOR_CONSULTA = "[TIPO:"
"""Prefill del turno de asistente para RESPONDEDOR_CONSULTA_DOCUMENTACION.

Fuerza que la respuesta EMPIECE por la marca de tipo, igual que el prefill "{"
fuerza JSON en `cliente_anthropic._pedir_json`. Sin espacios al final: la API
de Anthropic rechaza un prefill con whitespace final."""

MARCA_RESPUESTA_DIRECTA = "[TIPO:RESPUESTA]"
"""Marca que abre una respuesta normal (puede incluir incertidumbre o variantes)."""

MARCA_PREGUNTA_ACLARATORIA = "[TIPO:ACLARACION]"
"""Marca que abre UNA pregunta de vuelta al analista, en vez de una respuesta."""
```

The markers appear **literally** inside the prompt text (below) rather than being
interpolated with an f-string, so the prompt stays greppable and verbatim like every
other constant in this file. A test asserts both markers are substrings of the prompt, so
prompt/parser divergence fails in CI instead of in production.

#### New text: `RESPONDEDOR_CONSULTA_DOCUMENTACION`

```python
RESPONDEDOR_CONSULTA_DOCUMENTACION = """Respondés preguntas sobre cómo funciona un sistema para analistas que entienden de software pero no son programadores. Usás la documentación interna que se te da como contexto. Los analistas a veces llaman "solución" a lo que técnicamente es un módulo — entendé el término según el contexto, no lo tomes literal.

Tu salida SIEMPRE empieza con una de estas dos marcas, sin nada antes:

[TIPO:RESPUESTA] cuando podés responder con el contexto que recibiste.
[TIPO:ACLARACION] cuando la pregunta admite dos interpretaciones razonables y distintas que darían respuestas diferentes.

Cuándo pedir aclaración:

- Solo si la ambigüedad es real y cambia la respuesta. Si la pregunta es específica y el contexto resuelve una sola interpretación, respondé directo: una aclaración innecesaria le hace perder tiempo al analista.
- Cuando pedís aclaración escribís UNA sola pregunta, corta, que nombre las interpretaciones posibles. Nada más: ni respuesta parcial, ni varias preguntas, ni lista de opciones numeradas.
- Que la documentación esté incompleta NO es motivo de aclaración: eso se responde con [TIPO:RESPUESTA] diciendo qué parte queda sin confirmar.

Cómo responder:

- Analizá el contexto y explicá con tus propias palabras lo que encontraste; no lo copies ni lo resumas de forma genérica.
- Si el contexto resuelve solo una parte de la pregunta, respondé esa parte y decí explícitamente cuál queda sin confirmar. No presentes todo con la misma seguridad.
- Si el comportamiento cambia según el módulo o la configuración, decilo y describí las variantes que aparecen en el contexto. Nunca elijas una sola en silencio como si aplicara siempre.
- Si el contexto directamente no cubre la pregunta, decí que la documentación disponible no lo explica y qué haría falta para responderla. No uses la frase "No se encontró información sobre esto en la documentación disponible.": esa frase está reservada para cuando no se recuperó ningún documento, y repetirla acá borraría la diferencia entre los dos casos.
- Explicá SIEMPRE en términos de comportamiento y funcionalidad (qué hace el sistema, qué logra la persona usuaria), nunca de implementación. PROHIBIDO mencionar nombres de clases, funciones, tablas, campos o tipos de dato (entero, string, booleano, etc.), aunque aparezcan tal cual en el contexto — traducilos siempre a lo que significan para quien usa el sistema.
- No inventes causas internas ni comportamientos que el contexto no diga.
- Español neutro (sin voseo), lenguaje llano, sin preámbulo ni bloque de código."""
"""Prompt de sistema del modo consulta/Q&A: responde preguntas informativas
("cómo funciona X") usando solo la documentación recuperada, a diferencia
del modo de generación de tickets. Mismo nivel de "sin detalles de
implementación" que GENERADOR_DESCRIPCION_TICKET (regla 9), adaptado a
respuestas conversacionales en vez de un ticket — el público (analistas
no programadores) es el mismo.

Emite una de dos marcas de tipo al inicio (ver PREFILL_RESPONDEDOR_CONSULTA,
MARCA_RESPUESTA_DIRECTA, MARCA_PREGUNTA_ACLARATORIA); las parsea
`consultar_documentacion._interpretar_respuesta`. La marca no se le muestra
nunca al analista."""
```

Three text-level changes worth calling out because they are behavior, not wording:

| Change | Requirement it satisfies |
|---|---|
| The two `[TIPO:...]` marks + the "cuándo pedir aclaración" block, including the explicit *don't* case | `Clarifying Question on Ambiguous Query` — both scenarios (ambiguous asks, well-specified answers directly) |
| "decí explícitamente cuál queda sin confirmar" + "decilo y describí las variantes … nunca elijas una sola en silencio" | `Uncertainty and Variability Signaling` — both scenarios |
| **Removal** of the old bullet `Si el contexto no cubre la pregunta, decilo: "No se encontró información sobre esto en la documentación disponible."`, replaced by an explicit ban on that exact sentence | `No-Information Degrade Stays Distinct From Uncertainty`. **This is a real pre-existing defect the new spec exposes**: today the model is instructed to emit the reserved `SIN_INFORMACION` text while context *was* found, which collapses the two states the spec requires to stay distinguishable |

`Plain-Language, Non-Technical Answers` is already satisfied by the existing
implementation-detail bullet, kept verbatim, plus the added "no inventes causas internas".

### Infrastructure diffs (exact)

```diff
--- requirements.txt
 streamlit>=1.40
 elevenlabs>=2.0
-groq>=0.11
 anthropic>=1.3
 python-dotenv
 pytest
```

```diff
--- Dockerfile
-COPY app.py transcribir.py generar_descripcion.py contexto_memoria.py contexto_enriquecido.py consultar_documentacion.py prompts.py logging_config.py ./
+COPY app.py transcribir.py generar_descripcion.py contexto_memoria.py cliente_anthropic.py consultar_documentacion.py prompts.py logging_config.py ./
```

```diff
--- docker-compose.yml
     volumes:
       - ./logs:/app/logs
-      - ./cache/documentacion:/app/cache/documentacion
```

```diff
--- app.py
+from cliente_anthropic import ErrorConfiguracion
-from consultar_documentacion import responder_consulta
+from consultar_documentacion import (
+    TIPO_PREGUNTA_ACLARATORIA,
+    TIPO_RESPUESTA,
+    responder_consulta,
+)
 from contexto_memoria import diagnosticar, nombres_conocidos
 from generar_descripcion import (
-    ErrorConfiguracion,
     ErrorGeneracion,
     generar_descripcion,
 )
```

`app.py`'s `except ErrorConfiguracion` / `except ErrorGeneracion` handlers (lines 248-251)
are unchanged — the UI behavior for a missing key is byte-identical, only the key name in
the message changes.

### `app.py` — Q&A three-state rendering (`qa-documentacion`)

Today there is **no** state branching at all: `SIN_INFORMACION` is just a string that
lands in `st.session_state.resultado` and gets rendered by the same `st.text_area` as an
answer. The design keeps that single render path and adds the smallest thing that makes a
clarifying question unmistakable — one session-state field and the result card's
title/subtitle.

Session-state init (after the existing `resultado` init, line 168):

```diff
 if "resultado" not in st.session_state:
     st.session_state.resultado = ""
+if "tipo_respuesta" not in st.session_state:
+    st.session_state.tipo_respuesta = TIPO_RESPUESTA
```

Button handler (replaces lines 240-247):

```diff
             if modo == MODO_TICKET:
                 st.session_state.resultado = generar_descripcion(
                     st.session_state.transcripcion
                 )
+                st.session_state.tipo_respuesta = TIPO_RESPUESTA
             else:
-                st.session_state.resultado = responder_consulta(
+                respuesta = responder_consulta(
                     st.session_state.transcripcion
                 )
+                # `.texto` is always the analyst-facing string, so the text area
+                # keeps holding a plain str exactly as before.
+                st.session_state.resultado = respuesta.texto
+                st.session_state.tipo_respuesta = respuesta.tipo
```

Result card (replaces lines 253-258):

```diff
 if modo == MODO_TICKET:
     titulo_resultado = "Descripción para Jira"
     subtitulo_resultado = "El texto puede editarse antes de copiarlo al ticket."
+elif st.session_state.tipo_respuesta == TIPO_PREGUNTA_ACLARATORIA:
+    titulo_resultado = "BOB necesita una aclaración"
+    subtitulo_resultado = (
+        "La consulta admite más de una interpretación. Agregá el detalle que falta "
+        "a la transcripción y volvé a pulsar «Responder consulta»."
+    )
 else:
     titulo_resultado = "Respuesta"
     subtitulo_resultado = "Basada únicamente en la documentación disponible."
```

Everything below (the `st.markdown` card and the `st.text_area`) is **unchanged**.
Deliberately NOT added: a second widget, an `st.info` banner, an inline answer box for the
clarification, or auto-resubmission. The title/subtitle swap is what distinguishes the
state; anything more is UI redesign outside this change.

`TIPO_SIN_INFORMACION` gets **no** UI branch: today the notice renders in the answer box
and the spec only requires the states stay distinguishable, which they are at the API
boundary (`.tipo`) and by the notice's own fixed text. Adding a third header now would be
a UI change no requirement asks for.

Staleness: `tipo_respuesta` is reassigned on every button press in both modes, and the
clarification header only renders while `modo == MODO_CONSULTA`, so a stale header cannot
outlive the text it describes.

## Preserved contracts (must not regress)

| Contract | Where enforced after the change |
|---|---|
| `buscar_contexto()` NEVER raises; missing/unreadable `MEMORY_DIR` → `""` | Outer `except Exception` retained verbatim; it now also swallows `ErrorConfiguracion` from the new local `_crear_cliente()` call |
| Verifier defaults to keeping the analyst's text on ANY failure | `_verificar_resultado_esperado`'s `try/except Exception: return True` retained verbatim; `_pedir_json` raising on bad JSON lands there |
| Generation and Q&A fail fast on a missing key, before any network call | `_crear_cliente()` reads env only and raises `ErrorConfiguracion` before importing/constructing `Anthropic` |
| Q&A with no matching docs returns `SIN_INFORMACION` without needing a key | Client creation stays AFTER the context lookup (Decision 7). The text is byte-identical; only its wrapper changes (`RespuestaConsulta(SIN_INFORMACION, TIPO_SIN_INFORMACION)`) |
| A Q&A parse slip never destroys the answer and never fakes `SIN_INFORMACION` | `_interpretar_respuesta`'s final `return` keeps `texto_crudo` verbatim under `TIPO_RESPUESTA` (Decision 17) |
| `SIN_INFORMACION` and "uncertain answer" stay distinct | Different `tipo`, different call count (0 vs 1). The prompt is now explicitly banned from emitting the `SIN_INFORMACION` sentence itself |
| `st.session_state.resultado` stays a plain `str` | `app.py` assigns `respuesta.texto`, never the dataclass — `st.text_area(value=...)` contract unchanged |
| Selection never trusts an unlisted path | `elegir_documentos_relevantes`'s `rutas_validas` filter unchanged |
| Cross-batch re-rank corrects an early false positive | `_lotes_de_documentos` + final re-rank call unchanged; `CARACTERES_POR_LOTE` unchanged |
| No module imports Streamlit outside `app.py` | `cliente_anthropic.py` imports only stdlib + a lazy `anthropic` |
| Post-processor runs OUTSIDE the `ErrorGeneracion` try/except | Call position at the end of `generar_descripcion` unchanged |

## Testing Strategy

| Layer | What to test | Approach |
|---|---|---|
| Unit — `cliente_anthropic` | Missing/blank key raises before the SDK is touched; retry fires only on 429 with a fixed 5.0s wait and gives up after 3; `_texto_de` ignores non-text blocks; `_pedir_json` sends the prefill and parses, tolerates trailing prose, raises on garbage | `monkeypatch.delenv`, `monkeypatch.setattr(anthropic, "Anthropic", fail_if_called)`, `monkeypatch.setattr("cliente_anthropic.time.sleep", ...)`, `FakeAnthropic` |
| Unit — `generar_descripcion` | Fail-fast; request shape (`system=` top level, single user message, `model`/`temperature`/`max_tokens`); context vs no-context prompt selection; verifier called only when the section exists and only via prefill; every post-processor branch | `FakeAnthropic` discriminating on `system` |
| Unit — `contexto_memoria` | Selector request shape; batching + no-early-stop + cross-batch correction; `buscar_contexto` returns raw content verbatim, concatenates in selection order, degrades to `""` on every failure path including a missing key; a 40KB doc passes whole under the new budget | `FakeAnthropicSecuencia`, `_crear_arbol` tmp trees |
| Unit — `consultar_documentacion` | No context → `SIN_INFORMACION` with zero SDK construction; missing key + context → `ErrorConfiguracion`; request shape; SDK failure → `ErrorGeneracion`. **Plus: the three `tipo` values are produced and mutually exclusive; the tag is stripped from `.texto`; the assistant prefill is sent; an unknown/absent/mid-prose `]` degrades to `TIPO_RESPUESTA` with text intact** | `FakeAnthropic` (canned text **prefill-shaped** — no leading `[TIPO:`), `monkeypatch.setattr(anthropic, "Anthropic", ...)`, direct calls to the pure `_interpretar_respuesta` |
| Unit — prompt shape (`qa-documentacion`) | Both markers appear verbatim in `RESPONDEDOR_CONSULTA_DOCUMENTACION`; the prompt bans the `SIN_INFORMACION` sentence; the uncertainty/variability and one-question rules are present | Substring assertions on the constants, mirroring the existing `test_rule_N_*` prompt tests in `test_generar_descripcion.py` |
| Repo hygiene | No `.py` in the repo imports `groq`; `requirements.txt` has no `groq` line | `ast`/regex scan, mirroring the existing `test_no_inline_prompt_text_in_generar_descripcion` pattern |
| Manual smoke | Real `ANTHROPIC_API_KEY`, real 273-file corpus: one generation with `GROQ_API_KEY` unset; confirm the ticket cites document specifics and `logs/app.log` shows exactly 2-3 Anthropic calls. **Plus Q&A: (1) a specific question → answer, "Respuesta" header; (2) a deliberately vague question ("cómo funciona") → clarifying question, "BOB necesita una aclaración" header; (3) a question with no matching docs → the fixed notice with zero Anthropic calls in the log** | Documented in tasks. `app.py` has no test file (there is none today and this change does not add one) — the three-state UI branch is covered by manual smoke only |

### The `Fake` double shape (reused, not reinvented)

Lifted verbatim from today's `tests/test_contexto_enriquecido.py` — this is the whole
migration's reference double and every test file gets the same four classes:

```python
class FakeBloqueTexto:
    def __init__(self, text):
        self.type, self.text = "text", text


class FakeMensaje:
    def __init__(self, text):
        self.content = [FakeBloqueTexto(text)]


class FakeMessages:
    def __init__(self, respuesta="Descripción generada de prueba", error=None):
        self.calls, self._respuesta, self._error = [], respuesta, error

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return FakeMensaje(self._respuesta)


class FakeAnthropic:
    def __init__(self, respuesta="Descripción generada de prueba", error=None):
        self.messages = FakeMessages(respuesta, error)
```

Two file-local variants are needed:

```python
# tests/test_generar_descripcion.py — MODELO == MODELO_AUXILIAR now, so `model`
# can no longer tell the generation call from the verifier call (it could under
# Groq). Discriminate on `system` instead. A JSON answer is prefill-shaped: the
# fake returns the object body WITHOUT its leading "{".
class FakeMessages:
    def __init__(self, respuesta="Descripción generada de prueba", fundamentado=True):
        self.calls, self._respuesta, self._fundamentado = [], respuesta, fundamentado

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("system") == VERIFICADOR_RESULTADO_ESPERADO:
            return FakeMensaje(json.dumps({"fundamentado": self._fundamentado})[1:])
        return FakeMensaje(self._respuesta)
```

```python
# tests/test_contexto_memoria.py — canned selector answers, prefill-shaped.
class FakeMessagesSeleccion:
    def __init__(self, archivos_elegidos=None, error=None):
        self.calls = []
        self._archivos = archivos_elegidos if archivos_elegidos is not None else []
        self._error = error

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return FakeMensaje(json.dumps({"archivos": self._archivos})[1:])


class FakeAnthropicSecuencia:
    """A different canned `archivos` answer per call, in order — for the
    multi-batch / cross-batch re-rank tests. Replaces FakeGroqSecuencia."""

    def __init__(self, respuestas):
        self.messages = FakeMessagesSecuencia(respuestas)
```

### `tests/test_cliente_anthropic.py` (renamed from `test_contexto_enriquecido.py`)

Keep: the `FakeBloqueTexto`/`FakeMensaje`/`FakeMessages`/`FakeAnthropic` classes and the
`_sin_clave_anthropic` autouse fixture.

**Delete all 11 existing tests** (every one is enrichment or cache specific):
`test_cache_hit_performs_zero_api_calls`, `test_changed_content_triggers_a_fresh_call`,
`test_missing_api_key_returns_raw_content_and_never_raises`,
`test_api_error_for_one_document_degrades_only_that_block`,
`test_empty_haiku_response_degrades_to_raw`,
`test_unwritable_cache_directory_still_returns_the_summary`,
`test_order_preserved_when_a_later_document_completes_first`,
`test_enriquecer_documentos_returns_empty_list_for_empty_input`,
`test_hash_contenido_is_sha256_of_raw_bytes`,
`test_resolver_directorio_cache_explicit_arg_wins`,
`test_resolver_directorio_cache_defaults`.
`FakeMessagesPorIndice`/`FakeAnthropicPorIndice` are deleted with them (nothing fans out
concurrently any more).

**Add:**
`test_missing_key_raises_error_configuracion_before_sdk_construction`,
`test_blank_key_raises_error_configuracion`,
`test_crear_cliente_passes_the_key_to_anthropic`,
`test_texto_de_concatena_solo_bloques_de_texto`,
`test_texto_de_vacio_cuando_no_hay_bloques_de_texto`,
`test_reintento_no_op_on_success`,
`test_reintento_retries_on_rate_limit_then_succeeds` (asserts `esperas == [5.0]`),
`test_reintento_gives_up_after_max_attempts`,
`test_reintento_does_not_retry_non_rate_limit_errors`,
`test_pedir_json_envia_prefill_de_asistente_y_parsea`
(asserts `messages[-1] == {"role": "assistant", "content": "{"}`, `system`, `model`,
`temperature == 0.0`, and that no `response_format` kwarg is sent),
`test_pedir_json_tolera_texto_despues_del_objeto`,
`test_pedir_json_propaga_error_con_respuesta_no_json`,
`test_no_module_or_test_imports_groq`,
`test_requirements_no_longer_lists_groq`.

### `tests/test_generar_descripcion.py`

Imports: drop `import groq as groq_module`, `_crear_completion_con_reintento`,
`MAX_REINTENTOS_RATE_LIMIT`, `ErrorConfiguracion`; add `from cliente_anthropic import
ErrorConfiguracion` and `from prompts import VERIFICADOR_RESULTADO_ESPERADO`. Delete the
`FakeMessage`/`FakeChoice`/`FakeResponse`/`FakeCompletions`/`FakeChat`/`FakeGroq` block and
the `ErrorRateLimitFalso`/`ErrorNoRateLimitFalso` classes.

| Test | Change |
|---|---|
| `test_missing_key_raises_error_configuracion_before_any_call` | `GROQ_API_KEY`→`ANTHROPIC_API_KEY`; monkeypatch `anthropic.Anthropic` |
| `test_blank_key_raises_error_configuracion` | same |
| `test_generar_descripcion_with_injected_client` | `cliente.messages.calls`; system prompt now `kwargs["system"]`, user message now `messages[0]["content"]` |
| `test_no_context_provider_sends_byte_identical_prompt` | same relocation |
| `test_context_provider_with_match_uses_prompt_con_contexto` | same relocation |
| `test_context_provider_receives_the_transcript` | fake type only |
| `test_default_context_provider_is_contexto_memoria_buscar_contexto` | env var name; `kwargs["system"]`; **add** an assertion that exactly one call happened (proves the shared client reached `buscar_contexto`, which returned `""` before any selector call) |
| `test_synthetic_submodule_context_reaches_user_message_verbatim` | same relocation |
| `test_full_template_response_starts_with_modulo_and_contains_que_paso` | fake type + env var |
| `test_response_without_steps_omits_pasos_heading` | fake type + env var |
| `test_response_without_expectation_omits_resultado_heading` | fake type + env var |
| `test_response_falls_back_to_modulo_no_identificado` | fake type + env var |
| `test_response_has_no_code_fence` | fake type + env var |
| `test_generar_descripcion_calls_verifier_when_resultado_esperado_present` | `messages.calls`; **the `response_format == {"type":"json_object"}` assertion is invalid and must be replaced** by `system == VERIFICADOR_RESULTADO_ESPERADO` + `messages[-1] == {"role":"assistant","content":"{"}`; `model == MODELO_AUXILIAR` stays |
| `test_generar_descripcion_no_verifier_call_when_no_resultado_section` | `messages.calls` |
| `test_postprocesar_verifier_says_grounded_keeps_text` | fake type |
| `test_postprocesar_verifier_says_not_grounded_replaces_with_notice` | fake type |
| `test_postprocesar_verifier_exception_defaults_to_keeping_text` | `ClienteRoto` restructured to `.messages.create` |
| `test_postprocesar_verifier_malformed_json_defaults_to_keeping_text` | `ClienteRespuestaInvalida` returns `FakeMensaje("esto no es json")` via `.messages.create` |
| `test_postprocesar_absent_section_is_a_no_op_and_skips_verifier` | `cliente.messages.calls == []` |
| `test_postprocesar_empty_body_becomes_notice_without_calling_verifier` | `cliente.messages.calls == []` |
| `test_postprocesar_strips_wrapping_fence_keeps_inner_fence` | `cliente.messages.calls == []` |
| `test_postprocesar_non_string_content_tolerates_none` | fake type |
| `test_postprocesar_blank_string_passthrough` | fake type |
| `test_fake_groq_canned_response_round_trips_unchanged` | **rename** → `test_fake_anthropic_canned_response_round_trips_unchanged` |
| `test_reintento_no_op_on_success` | **move** to `test_cliente_anthropic.py` |
| `test_reintento_retries_on_rate_limit_then_succeeds` | **move + rewrite**: fixed `[5.0]`, no parsed wait |
| `test_reintento_gives_up_after_max_attempts` | **move** |
| `test_reintento_does_not_retry_non_rate_limit_errors` | **move** |
| `test_reintento_falls_back_to_default_wait_when_message_unparseable` | **delete** — no wait-text parsing exists on Anthropic |

Unchanged: `test_system_prompts_embed_plantilla_ticket_jira_verbatim`,
`test_template_headings_appear_in_fixed_order`,
`test_rule_5_prohibits_inventing_generic_expectation`,
`test_rules_3_and_4_require_full_omission_no_placeholder`,
`test_rule_6_modulo_afectado_fallback_literal`, `test_rule_7_requires_neutral_spanish`,
`test_rule_12_no_fence_no_preamble_wording`,
`test_context_rules_13_to_19_only_in_con_contexto_prompt`,
`test_rule_15_allows_module_functionality_only_in_contexto_del_modulo_section`,
`test_rule_16_context_facts_confined_to_contexto_del_modulo_section`,
`test_rule_19_still_bans_literal_copying_and_context_leaking_into_steps`,
`test_no_inline_prompt_text_in_generar_descripcion`.

### `tests/test_contexto_memoria.py`

Replace `FakeMessage`/`FakeChoice`/`FakeResponse`/`FakeCompletions`/`FakeChat`/`FakeGroq`/
`FakeCompletionsSecuencia`/`FakeGroqSecuencia` with the `FakeAnthropic*` family above.
Keep `_sin_clave_anthropic` and upgrade its docstring: it is no longer belt-and-braces,
it is the guard that stops `buscar_contexto`'s own `_crear_cliente()` from reaching the
network in the tests that do not inject a client.

| Test | Change |
|---|---|
| `test_elegir_documentos_relevantes_returns_empty_for_empty_listing` | fake type |
| `test_elegir_documentos_relevantes_filters_to_known_paths` | fake type |
| `test_elegir_documentos_relevantes_caps_at_max_archivos` | fake type |
| `test_elegir_documentos_relevantes_batches_large_listings` | `cliente.messages.calls` |
| `test_elegir_documentos_relevantes_scans_every_batch_no_early_stop` | `cliente.messages.calls` |
| `test_elegir_documentos_relevantes_final_call_corrects_early_false_positive` | `FakeAnthropicSecuencia`; `len(cliente.messages.calls) == 3` |
| `test_elegir_documentos_relevantes_sends_listing_and_transcript` | drop the `response_format` assertion; assert `kwargs["system"] == SELECTOR_DOCUMENTOS_RELEVANTES`, `kwargs["model"] == cm.MODELO_SELECTOR`, user message is `messages[0]["content"]` (was `messages[1]`) |
| `test_buscar_contexto_empty_when_no_documents` | `cliente.messages.calls == []` |
| `test_buscar_contexto_empty_when_selector_picks_nothing` | fake type |
| `test_buscar_contexto_degrades_to_empty_on_missing_directory` | fake type |
| `test_buscar_contexto_degrades_to_empty_on_selector_failure` | fake type |
| `test_buscar_contexto_never_raises_on_malformed_json` | `ClienteRespuestaInvalida` restructured to `.messages.create` returning `FakeMensaje("esto no es json")` |
| `test_buscar_contexto_uses_enriched_summary_instead_of_raw_content` | **delete** — the enrichment seam is gone |
| `test_buscar_contexto_falls_back_to_raw_content_when_enricher_fails` | **delete** |
| `test_buscar_contexto_falls_back_to_raw_content_on_enricher_length_mismatch` | **delete** |

**Add** (replacing the three deleted enrichment tests):

```python
def test_buscar_contexto_returns_selected_file_content_verbatim(tmp_path):
    """Restores the pre-enrichment contract: raw content, byte for byte."""
    raiz = _crear_arbol(
        tmp_path / "memory",
        {"riesgos/index.md": "Documentación real de riesgos.", "otro.md": "irrelevante"},
    )
    cliente = FakeAnthropic(archivos_elegidos=["riesgos/index.md"])

    contexto = cm.buscar_contexto("transcripción", directorio=str(raiz), cliente=cliente)

    assert contexto == "Documentación real de riesgos."


def test_buscar_contexto_concatenates_selected_docs_in_selection_order(tmp_path): ...
def test_buscar_contexto_injects_a_large_document_whole_under_the_new_budget(tmp_path): ...
    # 40 000-char doc: assert MARCADOR_TRUNCADO not in contexto — this is the
    # test that would have failed under the old 6 000-char budget.
def test_buscar_contexto_degrades_to_empty_when_key_missing_and_no_client_injected(tmp_path): ...
    # No `cliente=`, ANTHROPIC_API_KEY unset: ErrorConfiguracion must never escape.
```

Unchanged: every `resolver_directorio`, `listar_documentos`, `nombres_conocidos`,
`diagnosticar`, `_ensamblar_contexto` (both pass an explicit `presupuesto=`) and
`_resolver_seguro` test.

### `tests/test_consultar_documentacion.py`

Drop `import groq as groq_module` and the `FakeGroq` family; add the `FakeAnthropic` family.

**The fake's canned text is prefill-shaped** — the API never echoes the prefill, so a fake
answering `MARCA_RESPUESTA_DIRECTA + " El módulo…"` would be wrong. It must return
`"RESPUESTA] El módulo…"`, i.e. `MARCA_RESPUESTA_DIRECTA[len(PREFILL_RESPONDEDOR_CONSULTA):]`
plus the body — the same convention as the JSON fakes dropping their leading `{`.

Every existing assertion moves from a bare string to `.texto` / `.tipo`; the return type
change is intentionally loud, so `assert resultado == SIN_INFORMACION` fails rather than
silently passing.

| Test | Change |
|---|---|
| `test_no_context_returns_fixed_notice_without_any_network_call` | env var name; monkeypatch `anthropic.Anthropic` to `fail_if_called`; **assert `.texto == SIN_INFORMACION` AND `.tipo == TIPO_SIN_INFORMACION`** |
| `test_missing_key_raises_error_configuracion_when_context_exists` | env var name; import `ErrorConfiguracion` from `cliente_anthropic` |
| `test_responder_consulta_with_injected_client_and_context` | `cliente.messages.calls[0]`; `kwargs["system"] == RESPONDEDOR_CONSULTA_DOCUMENTACION`; user message is `messages[0]["content"]`; **assert `.texto` (tag stripped) and `.tipo == TIPO_RESPUESTA`** |
| `test_context_provider_receives_the_question` | fake type |
| `test_groq_failure_raises_error_generacion_with_friendly_message` | **rename** → `test_anthropic_failure_raises_error_generacion_with_friendly_message`; `ClienteRoto` restructured to `.messages.create` |

**Add** `test_injected_client_is_shared_with_the_default_context_provider` — asserts the
closure threads the injected client into `buscar_contexto` rather than building a second one.

**Add (`qa-documentacion`)** — the three states plus the parse contract:

```python
def test_request_sends_the_type_tag_prefill_as_the_last_message():
    # kwargs["messages"][-1] == {"role": "assistant", "content": PREFILL_RESPONDEDOR_CONSULTA}
    # and messages[0] is the user message — proves the tag is structural, not requested prose.

def test_respuesta_marker_is_stripped_from_the_analyst_facing_text():
    # fake returns "RESPUESTA] El módulo permite registrar riesgos."
    # -> .tipo == TIPO_RESPUESTA and "[TIPO:" not in .texto

def test_aclaracion_marker_returns_a_clarifying_question_state():
    # fake returns "ACLARACION] ¿Preguntás por el módulo de riesgos o por el de auditoría?"
    # -> .tipo == TIPO_PREGUNTA_ACLARATORIA and .texto is the question, tag-free

def test_unknown_marker_degrades_to_respuesta_keeping_the_full_text():
    # fake returns "OTRA_COSA] contenido real" -> .tipo == TIPO_RESPUESTA
    # and .texto == "[TIPO:OTRA_COSA] contenido real"  (nothing is lost)

def test_missing_marker_degrades_to_respuesta_keeping_the_full_text():
    # fake returns prose with no "]" at all -> TIPO_RESPUESTA, text intact

def test_a_closing_bracket_inside_the_prose_is_not_mistaken_for_a_marker():
    # fake returns "RESPUESTA] el campo [obligatorio] se valida" -> the FIRST "]"
    # is the real marker; body keeps its own brackets verbatim

def test_the_three_states_are_mutually_exclusive():
    # no-context / normal answer / clarifying question produce 3 distinct .tipo values,
    # and only the SIN_INFORMACION case made zero messages.create calls
```

Prompt-shape tests (same file, mirroring `test_generar_descripcion.py`'s `test_rule_N_*`):

```python
def test_prompt_declares_both_type_markers_verbatim():
    # MARCA_RESPUESTA_DIRECTA and MARCA_PREGUNTA_ACLARATORIA are substrings of
    # RESPONDEDOR_CONSULTA_DOCUMENTACION, and both start with
    # PREFILL_RESPONDEDOR_CONSULTA — this is what stops prompt/parser drift.

def test_prompt_no_longer_instructs_the_model_to_emit_the_sin_informacion_notice():
    # SIN_INFORMACION must NOT appear as an instruction the model should output;
    # the prompt must contain the explicit ban instead. Enforces
    # "No-Information Degrade Stays Distinct From Uncertainty".

def test_prompt_requires_signaling_uncertainty_and_variability():
    # "sin confirmar" / "variantes" wording present.

def test_prompt_limits_a_clarification_to_one_question():
    # "UNA sola pregunta" present, and the don't-over-ask rule is stated.
```

## Threat Matrix

N/A — no routing, shell command, subprocess, VCS/PR automation, executable-file
classification, or process-integration boundary is introduced or changed. This change
strictly *reduces* the filesystem write surface: the only writes the codebase performed
outside `logs/` were the enrichment cache files under `cache/documentacion/`, and those
are deleted. `MEMORY_DIR` access stays read-only with the existing symlink-escape guard
(`_resolver_seguro`) untouched.

## Migration / Rollout

Single PR, `size:exception` accepted (proposal decision 4 / user confirmation 4) —
forecast ~600-750 changed lines against the 400-line guard; no chaining.

**Revised forecast: ~800-950 changed lines.** The `qa-documentacion` addendum adds roughly
150-200 more (prompt rewrite ~35, `consultar_documentacion.py` ~60, `app.py` ~20, tests
~70). `sdd-tasks` must re-run the guard forecast on the new number; if the accepted
exception no longer covers it, the natural cut is a **second slice**: the provider
migration lands first (Q&A returning a plain `str` as today), then `qa-documentacion` on
top — the addendum touches only `prompts.py`, `consultar_documentacion.py`, `app.py` and
one test file, all of which the migration slice has already converted to Anthropic shapes.

No data migration and no persisted state to convert. Operator steps at deploy:

1. `pip install -r requirements.txt` (removing `groq` is optional locally; nothing imports it).
2. Ensure `ANTHROPIC_API_KEY` is set. `GROQ_API_KEY` becomes unused — harmless if left in `.env`.
3. `cache/documentacion/` is orphaned derived data; deleting it is safe and optional. It is
   gitignored, so nothing is committed either way.

Rollback: revert the merge commit. `groq>=0.11` returns to `requirements.txt`,
`GROQ_API_KEY` must be present again, the cache directory self-regenerates. Spec deltas
revert with the same commit.

There is no partial kill switch: unsetting `ANTHROPIC_API_KEY` now disables generation and
Q&A entirely (it previously only disabled enrichment). That is the intended consequence of
collapsing to one provider and is already the pre-existing behavior for `GROQ_API_KEY`.

## Open Questions

- [ ] **Per-document path headers in the raw context block.** Decision 10 keeps the blocks
      verbatim and unlabelled, matching the proposal wording. With up to 3 multi-KB raw
      documents concatenated by `\n\n`, the model cannot tell where one ends. Deferred to a
      prompt/context-format tuning change; revisit if the manual smoke test shows the ticket
      attributing content to the wrong screen.
- [ ] **`CARACTERES_POR_LOTE = 12000` is now conservative** — it was sized for Groq's 8000
      TPM free tier. Raising it would cut selector round trips on the 273-file corpus, but
      deliberately not in this PR (Decision 12). Measure real call counts post-merge.
- [ ] **`max_tokens=500` for the selector** was sized to absorb gpt-oss reasoning tokens
      that no longer exist. It is harmless (output-only cap) but could drop to ~200; left
      alone to keep the diff attributable.
- [ ] **`anthropic>=1.3` pinning.** Still a floor, not a pin, following the existing
      `streamlit>=1.40` convention. The `getattr(exc, "status_code", None) == 429` shape is
      verified against 1.3.0 only — re-verify if the floor is ever raised.
- [ ] **Clarification round-trip is one-shot, by design.** The analyst answers BOB's
      clarifying question by editing the transcription and pressing the button again; there
      is no conversation history, so the second call re-retrieves context and re-reads the
      whole edited text. That is sufficient for the spec (which only requires *returning* one
      clarifying question) and avoids adding a message-history seam to a stateless function.
      Revisit only if smoke testing shows analysts re-asking in circles.
- [ ] **`temperature=0.2` retained for Q&A.** `_pedir_json` pins 0.0 for structured calls,
      but Q&A keeps its existing 0.2 because the payload is prose. The tag is prefill-anchored,
      so temperature does not affect its reliability. Not changed in this PR.
- [ ] **Clarifying-question rate is unmeasured.** The prompt tells the model to prefer
      answering, but only live use will show whether it over-asks. If it does, the fix is
      prompt-level (tighten the "cuándo pedir aclaración" block), not structural — the
      transport supports either behavior.
- [ ] **`app.py` remains untested.** There is no `tests/test_app.py` today and this change
      does not add one, so the three-state UI branch is only covered by manual smoke. Flagged,
      not fixed here: adding Streamlit test infrastructure is its own change.
