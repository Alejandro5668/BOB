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
`postprocesar_descripcion`, a pure defense-in-depth pass over the raw
model output that replaces a generic-filler "Resultado esperado vs.
obtenido" body with a fixed notice. It runs OUTSIDE the try/except that
maps Groq SDK failures to `ErrorGeneracion`, so a post-processor bug can
never surface as a fake API error.
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from typing import Callable, Optional

from prompts import (
    ENTRADA_GENERADOR_DESCRIPCION,
    ENTRADA_GENERADOR_DESCRIPCION_CON_CONTEXTO,
    GENERADOR_DESCRIPCION_TICKET,
    GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO,
)

logger = logging.getLogger(__name__)

MODELO = "openai/gpt-oss-120b"  # llama-3.3-70b-versatile decommissioned by Groq, Aug 2026

ProveedorContexto = Callable[[str], str]

# --- Post-processor: heading + fixed notice ------------------------------

ENCABEZADO_RESULTADO = "## Resultado esperado vs. obtenido"
AVISO_RESULTADO_NO_CONFIABLE = (
    "Resultado esperado vs. obtenido: no se pudo determinar de forma confiable"
)

# Pinned blocklist (see design.md "Blocklist"): each entry is equally true
# of any incident in any module — zero transcript-specific information.
# Matching is always exact-fragment, never substring (see
# `es_relleno_generico`), so bare entries like "correctamente" are safe.
FRASES_GENERICAS = {
    # expectativa con verbo
    "funcionara correctamente",
    "funcionase correctamente",
    "funcione correctamente",
    "funcionara con normalidad",
    "funcionara de manera normal",
    "funcionara normalmente",
    "funcionara sin errores",
    "funcionara sin problemas",
    "funcionara sin inconvenientes",
    "operara con normalidad",
    "se comportara con normalidad",
    "se comportara correctamente",
    "cargara correctamente",
    "se cargara correctamente",
    "se mostrara correctamente",
    "se guardara correctamente",
    "se ejecutara correctamente",
    "se completara correctamente",
    "se procesara correctamente",
    "respondiera correctamente",
    "no presentara errores",
    "no presentara ningun error",
    "no fallara",
    "no diera error",
    "todo funcionara correctamente",
    "todo funcionara bien",
    "todo saliera bien",
    # sin verbo
    "un funcionamiento normal",
    "un comportamiento normal",
    "el funcionamiento esperado",
    "el comportamiento esperado",
    "el resultado esperado",
    "sin errores",
    "sin problemas",
    "sin inconvenientes",
    "sin fallos",
    "sin novedad",
    "de manera normal",
    "de forma normal",
    "con normalidad",
    "correctamente",
    # lado obtenido generico
    "no funciono correctamente",
    "no funciono como se esperaba",
    "no funciono",
    "no ocurrio lo esperado",
    "no se obtuvo el resultado esperado",
    "el resultado no fue el esperado",
    "el resultado fue distinto al esperado",
    "se obtuvo un resultado inesperado",
    "un comportamiento inesperado",
    "ocurrio un error",
    "se presento un error",
    "hubo un error",
    "hubo un fallo",
    "presento un error",
    "arrojo un error",
    "fallo",
}

# Scaffolding stripped iteratively from a fragment's start before matching
# it against FRASES_GENERICAS (see design.md "Post-Processor Interface").
_PATRONES_PREFIJO_RELLENO = (
    re.compile(r"^(?:el |la )?(?:resultado )?(?:esperado|obtenido|se obtuvo)\s*[:\-]?\s*"),
    re.compile(r"^(?:se )?(?:esperaba|espera|esperaria|deberia|debia)(?: de)?(?: que)?\s*"),
    re.compile(
        r"^(?:el sistema|la aplicacion|el aplicativo|el modulo|la pantalla|"
        r"la funcionalidad|el proceso|la opcion|el reporte|el formulario|"
        r"la pagina|la accion|todo|esto|ello)\s*"
    ),
    re.compile(r"^(?:que|y|pero|sin embargo|en su lugar|en cambio)\s*"),
)

_PATRON_CIFRA = re.compile(r"\d")
_PATRON_COMILLAS = re.compile(r'"[^"]+"|«[^»]+»')
_PATRON_MARCADOR_LISTA = re.compile(r"^\s*(?:[-*]|\d+\.)\s+")
_PATRON_FENCE_INICIO = re.compile(r"^```[a-zA-Z]*$")
_PATRON_FENCE_FIN = re.compile(r"^```$")


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
            "GROQ_API_KEY no está configurada. Define la variable de entorno "
            "(ver .env.example) antes de generar una descripción."
        )

    from groq import Groq

    return Groq(api_key=clave)


# --- Post-processor: pure str -> str, never raises -----------------------


def _normalizar_fragmento(fragmento: str) -> str:
    """NFKD accent-strip, lowercase, drop bold/backtick markers, collapse
    whitespace, strip trailing punctuation."""
    forma = unicodedata.normalize("NFKD", fragmento)
    sin_diacriticos = "".join(c for c in forma if not unicodedata.combining(c))
    minusculas = sin_diacriticos.lower()
    sin_marcas = re.sub(r"[*_`]", "", minusculas)
    colapsado = re.sub(r"\s+", " ", sin_marcas).strip()
    return colapsado.rstrip(".,;:!?")


def _quitar_relleno_estructural(fragmento: str) -> str:
    """Strip scaffolding prefixes (result marker, expectation verb, generic
    subject, connector) iteratively from the fragment start."""
    cambiado = True
    while cambiado:
        cambiado = False
        for patron in _PATRONES_PREFIJO_RELLENO:
            nuevo = patron.sub("", fragmento)
            if nuevo != fragmento:
                fragmento = nuevo
                cambiado = True
    return fragmento


def _fragmentos(cuerpo: str) -> list[str]:
    """Split on newlines, then list markers, then `.`/`;` — drop empties."""
    piezas: list[str] = []
    for linea in cuerpo.splitlines():
        sin_marcador = _PATRON_MARCADOR_LISTA.sub("", linea)
        for parte in re.split(r"[.;]+", sin_marcador):
            parte = parte.strip()
            if parte:
                piezas.append(parte)
    return piezas


def es_relleno_generico(cuerpo: str) -> bool:
    """True only when every fragment of `cuerpo` normalizes to an exact
    member of FRASES_GENERICAS after scaffolding is stripped. A digit, a
    backtick, or a quoted run anywhere makes the body genuine (False) —
    specificity always wins. Pure, total, exported for tests."""
    if _PATRON_CIFRA.search(cuerpo) or "`" in cuerpo or _PATRON_COMILLAS.search(cuerpo):
        return False

    fragmentos = _fragmentos(cuerpo)
    if not fragmentos:
        return False

    for fragmento in fragmentos:
        residuo = _quitar_relleno_estructural(_normalizar_fragmento(fragmento))
        if residuo and residuo not in FRASES_GENERICAS:
            return False
    return True


def postprocesar_descripcion(texto: str) -> str:
    """Best-effort defense-in-depth over the raw Groq response: strips a
    whole-output code fence and replaces a generic-filler
    `## Resultado esperado vs. obtenido` body with a fixed notice.

    Pure, total, never raises. Runs OUTSIDE the try/except that maps Groq
    SDK failures to `ErrorGeneracion` — a bug here must never surface as a
    fake API error. This is defense-in-depth only: the prompt template is
    the primary control against invented expectations.
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

    if cuerpo and not es_relleno_generico(cuerpo):
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
        logger.error(
            "Fallo en la llamada a Groq (modelo=%s): %s: %s",
            modelo, type(exc).__name__, exc,
        )
        raise ErrorGeneracion(
            "No se pudo generar la descripción (fallo de autenticación o de "
            "la API de Groq). Ver logs/app.log para el detalle técnico."
        ) from exc

    return postprocesar_descripcion(respuesta.choices[0].message.content)
