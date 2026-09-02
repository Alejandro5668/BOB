"""Documentation Q&A: answers an informational question ("cómo funciona
el módulo de riesgos") using ONLY retrieved `memory/` context, grounded
and analyzed rather than copy-pasted — a distinct mode from
`generar_descripcion.py`'s incident-ticket generation.

Reuses `cliente_anthropic`'s shared Haiku client (same `ANTHROPIC_API_KEY`,
same fail-fast behavior) and `contexto_memoria`'s schema-free retrieval —
no separate provider, no duplicated setup.

Never imports Streamlit. Client is always constructor-injected so unit
tests run with a fake client, same seam as `generar_descripcion`.

`responder_consulta()` returns a `RespuestaConsulta` distinguishing three
states: a direct answer (`TIPO_RESPUESTA`), a clarifying question back to
the analyst (`TIPO_PREGUNTA_ACLARATORIA`), or the fixed no-information
notice (`TIPO_SIN_INFORMACION`) — reserved for when retrieval finds no
relevant context at all, unchanged from before this change and still made
with zero network calls. Which state applies is discriminated on the wire
by an assistant-prefilled `[TIPO:...]` tag (see `prompts.py`), not by
searching the model's prose for a sentinel phrase.
"""

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
    Not an exception either: a clarifying question is a success outcome, not
    a failure `responder_consulta` should raise.
    """

    texto: str
    tipo: TipoRespuesta


ProveedorContexto = Callable[[str], str]


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


def responder_consulta(
    pregunta: str,
    *,
    proveedor_contexto: Optional[ProveedorContexto] = None,
    cliente=None,
    modelo: str = MODELO,
) -> RespuestaConsulta:
    """Answer `pregunta` using only retrieved `memory/` context.

    Returns `RespuestaConsulta(SIN_INFORMACION, TIPO_SIN_INFORMACION)` — no
    network call — when retrieval finds nothing relevant; there is genuinely
    nothing grounded to answer from. `cliente`/`proveedor_contexto` are
    injected for testing, mirroring `generar_descripcion.generar_descripcion`'s
    seams.

    When `cliente` IS injected, it is threaded into the default
    `proveedor_contexto` (`contexto_memoria.buscar_contexto`) so retrieval
    reuses the same Anthropic client. When `cliente` is None, no client is
    built just to attempt retrieval — hoisting client creation here would
    turn the "no key + no matching docs" case into a raised error instead
    of the silent `SIN_INFORMACION` degrade.
    """
    if proveedor_contexto is None:
        from contexto_memoria import buscar_contexto

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
            "Fallo en la llamada a Claude Haiku 4.5 (modelo=%s): %s: %s",
            modelo, type(exc).__name__, exc,
        )
        raise ErrorGeneracion(
            "No se pudo responder la consulta (fallo de autenticación o de "
            "la API de Anthropic). Ver logs/app.log para el detalle técnico."
        ) from exc

    # The prefill is not echoed by the API, so re-prepend it before parsing —
    # exactly as `_pedir_json` does with its "{".
    return _interpretar_respuesta(PREFILL_RESPONDEDOR_CONSULTA + _texto_de(respuesta))
