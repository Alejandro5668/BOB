"""Jira-ready description generation from an approved transcript via Groq.

Owns the entire prompt template and the Groq client lifecycle. The client
is always constructor-injected (never built at import time) so unit tests
run today with a fake client and the missing `GROQ_API_KEY` blocker never
breaks import or testing. Never imports Streamlit (see spec "Module
Testability").

Fase 2 adds an optional `proveedor_contexto` seam mirroring `cliente`:
when a module clears the retrieval threshold (see `contexto_memoria.py`),
its `_modulo.md` content is injected as a distinct, delimited context
block using `SYSTEM_PROMPT_CON_CONTEXTO`. When no context is returned,
the Groq request stays byte-identical to Fase 1 (`SYSTEM_PROMPT` +
`PLANTILLA_USUARIO`).
"""

from __future__ import annotations

import os
from typing import Callable, Optional

MODELO = "llama-3.3-70b-versatile"

ProveedorContexto = Callable[[str], str]

SYSTEM_PROMPT = """Eres un asistente que redacta descripciones de incidencias para tickets de Jira, en español.

Reglas obligatorias:
1. Escribe en prosa libre en español. Sin secciones, títulos, viñetas ni plantillas.
2. Usa lenguaje llano, comprensible para una persona no técnica.
3. Usa ÚNICAMENTE la información presente en la transcripción. No inventes datos.
4. PROHIBIDO mencionar o suponer detalles de implementación (nombres de clases, funciones, métodos, tablas, endpoints, consultas SQL) que no aparezcan literalmente en la transcripción.
5. PROHIBIDO diagnosticar la causa técnica. Describe solo el comportamiento observado: qué hacía la persona, qué esperaba y qué ocurrió.
6. Si un dato no está en la transcripción (versión, usuario, entorno, pasos exactos), omítelo; no lo supongas ni pongas marcadores de posición.
7. Responde solo con la descripción, sin preámbulos ni markdown."""

PLANTILLA_USUARIO = """Transcripción del analista:
---
{transcripcion}
---
Redacta la descripción."""

REGLAS_CONTEXTO = """Reglas adicionales para el bloque "Contexto de módulo":
8. El contexto es documentación interna de referencia. Úsalo SOLO para nombrar correctamente el módulo afectado y su comportamiento documentado.
9. La transcripción es la única fuente de los hechos del incidente. PROHIBIDO presentar contenido del contexto como algo que ocurrió, se observó o se hizo.
10. PROHIBIDO afirmar o insinuar cualquier cosa sobre el módulo que no aparezca literalmente en el bloque de contexto.
11. Si el contexto no concuerda con lo narrado en la transcripción, IGNÓRALO por completo y redacta únicamente desde la transcripción.
12. PROHIBIDO enumerar funcionalidades del módulo, copiar frases del contexto o mencionar que existe un contexto."""

SYSTEM_PROMPT_CON_CONTEXTO = SYSTEM_PROMPT + "\n\n" + REGLAS_CONTEXTO

PLANTILLA_USUARIO_CON_CONTEXTO = """Contexto de módulo (documentación interna, solo referencia):
===
{contexto}
===
Transcripción del analista:
---
{transcripcion}
---
Redacta la descripción. Los hechos salen solo de la transcripción; el contexto solo sirve para nombrar el módulo y su comportamiento documentado."""


class ErrorConfiguracion(RuntimeError):
    """Raised when GROQ_API_KEY is absent/blank — before any HTTP call."""


class ErrorGeneracion(RuntimeError):
    """Raised on Groq SDK auth/API failures. Never includes the key value."""


def _crear_cliente():
    """Build the Groq client, failing fast if the API key is not set.

    Reads GROQ_API_KEY only from the environment. Raises ErrorConfiguracion
    before any network call if the value is absent or blank.
    """
    clave = os.environ.get("GROQ_API_KEY", "").strip()
    if not clave:
        raise ErrorConfiguracion(
            "GROQ_API_KEY no está configurada. Define la variable de entorno "
            "(ver .env.example) antes de generar una descripción."
        )

    from groq import Groq

    return Groq(api_key=clave)


def generar_descripcion(
    transcripcion: str,
    *,
    proveedor_contexto: Optional[ProveedorContexto] = None,
    cliente=None,
    modelo: str = MODELO,
) -> str:
    """Send `transcripcion` (plus retrieved module context, if any) to Groq.

    `cliente` is injected for testing; when None, `_crear_cliente()` is
    called, which fails fast on a missing/blank GROQ_API_KEY — before any
    context retrieval or network call.

    `proveedor_contexto` is injected for testing; when None, it resolves
    lazily to `contexto_memoria.buscar_contexto` (a total function that
    never raises and returns `""` on no-match/missing/unreadable memory).
    When it returns a non-empty string, the Groq request uses
    `SYSTEM_PROMPT_CON_CONTEXTO` and the context-block user template.
    Otherwise the request stays byte-identical to Fase 1.
    """
    if cliente is None:
        cliente = _crear_cliente()

    if proveedor_contexto is None:
        from contexto_memoria import buscar_contexto as proveedor_contexto

    contexto = proveedor_contexto(transcripcion)

    if contexto:
        system_prompt = SYSTEM_PROMPT_CON_CONTEXTO
        mensaje_usuario = PLANTILLA_USUARIO_CON_CONTEXTO.format(
            contexto=contexto, transcripcion=transcripcion
        )
    else:
        system_prompt = SYSTEM_PROMPT
        mensaje_usuario = PLANTILLA_USUARIO.format(transcripcion=transcripcion)

    try:
        respuesta = cliente.chat.completions.create(
            model=modelo,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": mensaje_usuario},
            ],
            temperature=0.2,
            max_tokens=1024,
        )
    except Exception as exc:
        raise ErrorGeneracion(
            "No se pudo generar la descripción (fallo de autenticación o de "
            "la API de Groq)."
        ) from exc

    return respuesta.choices[0].message.content
