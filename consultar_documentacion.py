"""Documentation Q&A: answers an informational question ("cómo funciona
el módulo de riesgos") using ONLY retrieved `memory/` context, grounded
and analyzed rather than copy-pasted — a distinct mode from
`generar_descripcion.py`'s incident-ticket generation.

Reuses the shared Anthropic client toolkit (`cliente_anthropic.py`, same
`ANTHROPIC_API_KEY`, same fail-fast behavior) and `contexto_memoria`'s
schema-free retrieval — no separate provider, no duplicated setup.

Never imports Streamlit. Client is always constructor-injected so unit
tests run with a fake client, same seam as `generar_descripcion`.

NOTE: this PR only repoints the provider (Groq -> Claude Haiku 4.5).
`responder_consulta()` keeps returning a plain `str` here — the 3-state
`RespuestaConsulta` return contract (answer / clarifying question /
no-information) is a separate, later change.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from cliente_anthropic import (
    MODELO_HAIKU,
    _crear_cliente,
    _crear_mensaje_con_reintento,
    _texto_de,
)
from generar_descripcion import ErrorGeneracion
from prompts import ENTRADA_RESPONDEDOR_CONSULTA, RESPONDEDOR_CONSULTA_DOCUMENTACION

logger = logging.getLogger(__name__)

MODELO = MODELO_HAIKU

SIN_INFORMACION = "No se encontró información sobre esto en la documentación disponible."

ProveedorContexto = Callable[[str], str]


def responder_consulta(
    pregunta: str,
    *,
    proveedor_contexto: Optional[ProveedorContexto] = None,
    cliente=None,
    modelo: str = MODELO,
) -> str:
    """Answer `pregunta` using only retrieved `memory/` context.

    Returns the fixed `SIN_INFORMACION` notice — no network call — when
    retrieval finds nothing relevant; there is genuinely nothing grounded
    to answer from. `cliente`/`proveedor_contexto` are injected for
    testing, mirroring `generar_descripcion.generar_descripcion`'s seams.

    When `cliente` IS injected, it is threaded into the default
    `proveedor_contexto` (`contexto_memoria.buscar_contexto`) so retrieval
    reuses the same Anthropic client. When `cliente` is None, no client is
    built just to attempt retrieval — hoisting client creation here would
    turn the "no key + no matching docs" case into a raised error instead
    of the silent `SIN_INFORMACION` degrade.
    """
    if proveedor_contexto is None:
        from contexto_memoria import buscar_contexto

        def proveedor_contexto(texto):
            return buscar_contexto(texto, cliente=cliente)

    contexto = proveedor_contexto(pregunta)
    if not contexto:
        return SIN_INFORMACION

    if cliente is None:
        cliente = _crear_cliente()

    mensaje_usuario = ENTRADA_RESPONDEDOR_CONSULTA.format(contexto=contexto, pregunta=pregunta)

    try:
        respuesta = _crear_mensaje_con_reintento(
            cliente,
            model=modelo,
            system=RESPONDEDOR_CONSULTA_DOCUMENTACION,
            messages=[{"role": "user", "content": mensaje_usuario}],
            max_tokens=1024,
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

    return _texto_de(respuesta)
