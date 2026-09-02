"""Jira-ready description generation from an approved transcript via Groq.

Owns the Groq client lifecycle and the best-effort output post-processor.
Prompt text lives in `prompts.py` (see CLAUDE.md "Prompt repository
convention") — this module imports it, never defines it inline. The client
is always constructor-injected (never built at import time) so unit tests
run today with a fake client and the missing `GROQ_API_KEY` blocker never
breaks import or testing. Never imports Streamlit (see spec "Module
Testability").

Fase 2 adds an optional `proveedor_contexto` seam mirroring `cliente`:
when a module clears the retrieval threshold (see `contexto_memoria.py`),
its `_modulo.md` content is injected as a distinct, delimited context
block using `GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO`. When no context is
returned, the Groq request stays byte-identical to the no-context path
(`GENERADOR_DESCRIPCION_TICKET` + `ENTRADA_GENERADOR_DESCRIPCION`).

Fase 3 adds a locked Markdown ticket template (see `prompts.py`) plus
`postprocesar_descripcion`, a defense-in-depth pass over the raw model
output. It strips a whole-output code fence, and — when a "Resultado
esperado vs. obtenido" section is present — asks Groq itself (a cheap
auxiliary model, see `MODELO_AUXILIAR`) whether it's explicitly grounded
in the transcript; an earlier fixed-phrase blocklist was replaced with
this model judgment call at the user's explicit request, since a fixed
list can never cover every way of phrasing an invented expectation. It
runs OUTSIDE the try/except that maps Groq SDK failures to
`ErrorGeneracion`, so a post-processor bug (including the verifier call
itself failing) can never surface as a fake API error — on failure it
defaults to keeping the model's original text.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Callable, Optional

from prompts import (
    ENTRADA_GENERADOR_DESCRIPCION,
    ENTRADA_GENERADOR_DESCRIPCION_CON_CONTEXTO,
    GENERADOR_DESCRIPCION_TICKET,
    GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO,
)

logger = logging.getLogger(__name__)

MODELO = "openai/gpt-oss-120b"  # llama-3.3-70b-versatile decommissioned by Groq, Aug 2026
# gpt-oss models reason internally before answering, and those reasoning
# tokens count against max_tokens — a too-small cap cuts reasoning off
# mid-thought, leaving an empty completion Groq's JSON mode then rejects
# (400). reasoning_effort="low" keeps that cost small (see contexto_memoria.py
# for the measured before/after).
MODELO_AUXILIAR = "openai/gpt-oss-20b"  # cheaper/faster, used for the verifier call only

ProveedorContexto = Callable[[str], str]

# --- Post-processor: heading + fixed notice ------------------------------

ENCABEZADO_RESULTADO = "## Resultado esperado vs. obtenido"
AVISO_RESULTADO_NO_CONFIABLE = (
    "Resultado esperado vs. obtenido: no se pudo determinar de forma confiable"
)

_PATRON_FENCE_INICIO = re.compile(r"^```[a-zA-Z]*$")
_PATRON_FENCE_FIN = re.compile(r"^```$")

# Groq's free-tier TPM limit is an aggregate across ALL calls in the same
# rolling minute — a single query that needs several selector batches
# (contexto_memoria.py) plus generation plus verification can exceed it
# even though no single call is oversized (confirmed live against the
# real 273-file Kawak corpus). Groq's own error message names the exact
# wait time ("...please try again in 22.5s"); retrying after that instead
# of failing lets one query safely span more than a minute.
_PATRON_ESPERA_RATE_LIMIT = re.compile(r"try again in ([\d.]+)s", re.IGNORECASE)
MAX_REINTENTOS_RATE_LIMIT = 3


def _crear_completion_con_reintento(cliente, **kwargs):
    """`cliente.chat.completions.create(**kwargs)`, retrying on a 429
    rate-limit response by waiting the delay Groq reports in the error
    message. Shared by every Groq-calling module in this project
    (contexto_memoria.py, consultar_documentacion.py) — import from here
    rather than duplicating."""
    intentos = 0
    while True:
        try:
            return cliente.chat.completions.create(**kwargs)
        except Exception as exc:
            es_rate_limit = getattr(exc, "status_code", None) == 429
            intentos += 1
            if not es_rate_limit or intentos > MAX_REINTENTOS_RATE_LIMIT:
                raise
            coincidencia = _PATRON_ESPERA_RATE_LIMIT.search(str(exc))
            espera = float(coincidencia.group(1)) + 1 if coincidencia else 5.0
            logger.warning(
                "Rate limit de Groq alcanzado, reintentando en %.1fs (intento %d/%d)",
                espera, intentos, MAX_REINTENTOS_RATE_LIMIT,
            )
            time.sleep(espera)


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
        logger.warning("GROQ_API_KEY ausente o vacía al intentar generar una descripción.")
        raise ErrorConfiguracion(
            "GROQ_API_KEY no está configurada. Debe definirse la variable de "
            "entorno (ver .env.example) antes de generar una descripción."
        )

    from groq import Groq

    return Groq(api_key=clave)


# --- Post-processor: fence-strip (pure) + Groq-judged grounding check ----


def _verificar_resultado_esperado(transcripcion: str, cuerpo: str, cliente) -> bool:
    """Ask Groq whether `cuerpo` is explicitly grounded in `transcripcion`,
    or an invented/generic expectation nobody stated.

    Defaults to True (assume grounded, keep the text) on any failure — a
    broken verifier must never silently erase real analyst-provided
    content. Never raises.
    """
    from prompts import (
        ENTRADA_VERIFICADOR_RESULTADO_ESPERADO,
        VERIFICADOR_RESULTADO_ESPERADO,
    )

    try:
        respuesta = _crear_completion_con_reintento(
            cliente,
            model=MODELO_AUXILIAR,
            messages=[
                {"role": "system", "content": VERIFICADOR_RESULTADO_ESPERADO},
                {
                    "role": "user",
                    "content": ENTRADA_VERIFICADOR_RESULTADO_ESPERADO.format(
                        transcripcion=transcripcion, cuerpo=cuerpo
                    ),
                },
            ],
            temperature=0.0,
            max_tokens=150,
            reasoning_effort="low",
            response_format={"type": "json_object"},
        )
        datos = json.loads(respuesta.choices[0].message.content)
        return bool(datos.get("fundamentado", True))
    except Exception as exc:
        logger.warning(
            "Verificación de 'Resultado esperado' falló, se conserva el texto: %s: %s",
            type(exc).__name__, exc,
        )
        return True


def postprocesar_descripcion(texto: str, transcripcion: str, cliente) -> str:
    """Best-effort defense-in-depth over the raw Groq response: strips a
    whole-output code fence, and — when a "Resultado esperado vs. obtenido"
    section is present — asks Groq itself whether it's grounded in
    `transcripcion`; if not, replaces it with a fixed notice.

    Never raises. Runs OUTSIDE the try/except that maps Groq SDK failures
    to `ErrorGeneracion` for the main generation call — a bug here
    (including the verifier call itself failing) degrades to keeping the
    model's original text, never surfaces as a fake generation error.
    """
    if not isinstance(texto, str) or not texto.strip():
        return texto or ""

    resultado = texto
    lineas = resultado.split("\n")

    if (
        len(lineas) >= 2
        and _PATRON_FENCE_INICIO.match(lineas[0])
        and _PATRON_FENCE_FIN.match(lineas[-1])
    ):
        lineas = lineas[1:-1]
        resultado = "\n".join(lineas)

    indice_encabezado = None
    for i, linea in enumerate(lineas):
        if linea.strip().rstrip(":") == ENCABEZADO_RESULTADO:
            indice_encabezado = i
            break

    if indice_encabezado is None:
        return resultado

    fin_cuerpo = len(lineas)
    for j in range(indice_encabezado + 1, len(lineas)):
        if lineas[j].startswith("## "):
            fin_cuerpo = j
            break

    cuerpo = "\n".join(lineas[indice_encabezado + 1 : fin_cuerpo]).strip()

    if cuerpo and _verificar_resultado_esperado(transcripcion, cuerpo, cliente):
        return resultado

    reemplazo = [AVISO_RESULTADO_NO_CONFIABLE]
    if fin_cuerpo < len(lineas):
        reemplazo.append("")

    nuevas_lineas = lineas[: indice_encabezado + 1] + reemplazo + lineas[fin_cuerpo:]
    return "\n".join(nuevas_lineas)


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
    `GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO` and the context-block user
    template. Otherwise the request stays byte-identical to the no-context
    path.

    The raw Groq response is passed through `postprocesar_descripcion`
    before it is returned (outside the try/except below).
    """
    if cliente is None:
        cliente = _crear_cliente()

    if proveedor_contexto is None:
        from contexto_memoria import buscar_contexto as proveedor_contexto

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
        respuesta = _crear_completion_con_reintento(
            cliente,
            model=modelo,
            messages=[
                {"role": "system", "content": system_prompt},
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
            "No se pudo generar la descripción (fallo de autenticación o de "
            "la API de Groq). Ver logs/app.log para el detalle técnico."
        ) from exc

    return postprocesar_descripcion(respuesta.choices[0].message.content, transcripcion, cliente)
