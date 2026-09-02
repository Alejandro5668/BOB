"""Documentation Q&A: answers an informational question ("cómo funciona
el módulo de riesgos") using ONLY retrieved `memory/` context, grounded
and analyzed rather than copy-pasted — a distinct mode from
`generar_descripcion.py`'s incident-ticket generation.

Reuses `generar_descripcion`'s Groq client construction (same
GROQ_API_KEY, same fail-fast behavior) and `contexto_memoria`'s
schema-free retrieval — no separate provider, no duplicated setup.

Never imports Streamlit. Client is always constructor-injected so unit
tests run with a fake client, same seam as `generar_descripcion`.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from generar_descripcion import ErrorGeneracion, _crear_cliente, _crear_completion_con_reintento
from prompts import ENTRADA_RESPONDEDOR_CONSULTA, RESPONDEDOR_CONSULTA_DOCUMENTACION

logger = logging.getLogger(__name__)

MODELO = "openai/gpt-oss-120b"

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
    """
    if proveedor_contexto is None:
        from contexto_memoria import buscar_contexto as proveedor_contexto

    contexto = proveedor_contexto(pregunta)
    if not contexto:
        return SIN_INFORMACION

    if cliente is None:
        cliente = _crear_cliente()

    mensaje_usuario = ENTRADA_RESPONDEDOR_CONSULTA.format(contexto=contexto, pregunta=pregunta)

    try:
        respuesta = _crear_completion_con_reintento(
            cliente,
            model=modelo,
            messages=[
                {"role": "system", "content": RESPONDEDOR_CONSULTA_DOCUMENTACION},
                {"role": "user", "content": mensaje_usuario},
            ],
            temperature=0.2,
            max_tokens=1024,
        )
    except Exception as exc:
        logger.error(
            "Fallo en la llamada a Groq (modelo=%s): %s: %s",
            modelo, type(exc).__name__, exc,
        )
        raise ErrorGeneracion(
            "No se pudo responder la consulta (fallo de autenticación o de "
            "la API de Groq). Ver logs/app.log para el detalle técnico."
        ) from exc

    return respuesta.choices[0].message.content
