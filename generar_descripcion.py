"""Jira-ready description generation from an approved transcript via Groq.

Owns the entire prompt template and the Groq client lifecycle. The client
is always constructor-injected (never built at import time) so unit tests
run today with a fake client and the missing `GROQ_API_KEY` blocker never
breaks import or testing. Never imports Streamlit (see spec "Module
Testability").
"""

from __future__ import annotations

import os
from typing import Optional

MODELO = "llama-3.3-70b-versatile"

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
    cliente=None,
    modelo: str = MODELO,
) -> str:
    """Send only `transcripcion` to Groq and return the generated prose.

    `cliente` is injected for testing; when None, `_crear_cliente()` is
    called, which fails fast on a missing/blank GROQ_API_KEY.
    """
    if cliente is None:
        cliente = _crear_cliente()

    mensaje_usuario = PLANTILLA_USUARIO.format(transcripcion=transcripcion)

    try:
        respuesta = cliente.chat.completions.create(
            model=modelo,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
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
