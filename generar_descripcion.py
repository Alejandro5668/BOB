"""Jira-ready description generation from an approved transcript via Claude
Haiku 4.5 (see `cliente_anthropic.py` for the shared client/retry toolkit).

Prompt text lives in `prompts.py` (see CLAUDE.md "Prompt repository
convention") — this module imports it, never defines it inline. The client
is always constructor-injected (never built at import time) so unit tests
run today with a fake client and the missing `ANTHROPIC_API_KEY` blocker
never breaks import or testing. Never imports Streamlit (see spec "Module
Testability").

Fase 2 adds an optional `proveedor_contexto` seam mirroring `cliente`:
when a module clears the retrieval threshold (see `contexto_memoria.py`),
its raw documentation content is injected as a distinct, delimited context
block using `GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO`. When no context is
returned, the request stays byte-identical to the no-context path
(`GENERADOR_DESCRIPCION_TICKET` + `ENTRADA_GENERADOR_DESCRIPCION`). The
client built here is threaded into the default context provider so
selection, generation, and verification share one Anthropic client per
top-level request (see cliente_anthropic.py design decision on client
sharing).

Fase 3 adds a locked Markdown ticket template (see `prompts.py`) plus
`postprocesar_descripcion`, a defense-in-depth pass over the raw model
output. It strips a whole-output code fence, and — when a "Resultado
esperado vs. obtenido" section is present — asks Claude Haiku 4.5 itself
(a cheap auxiliary call, see `MODELO_AUXILIAR`) whether it's explicitly
grounded in the transcript; an earlier fixed-phrase blocklist was replaced
with this model judgment call at the user's explicit request, since a
fixed list can never cover every way of phrasing an invented expectation.
It runs OUTSIDE the try/except that maps Anthropic SDK failures to
`ErrorGeneracion`, so a post-processor bug (including the verifier call
itself failing) can never surface as a fake API error — on failure it
defaults to keeping the model's original text.
"""

from __future__ import annotations

import logging
import re
from typing import Callable, Optional

from cliente_anthropic import (
    ErrorConfiguracion,
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
MODELO_AUXILIAR = MODELO_HAIKU  # same model id; kept as a distinct public kwarg name

ProveedorContexto = Callable[[str], str]

# --- Post-processor: heading + fixed notice ------------------------------

ENCABEZADO_RESULTADO = "## Resultado esperado vs. obtenido"
AVISO_RESULTADO_NO_CONFIABLE = (
    "Resultado esperado vs. obtenido: no se pudo determinar de forma confiable"
)

_PATRON_FENCE_INICIO = re.compile(r"^```[a-zA-Z]*$")
_PATRON_FENCE_FIN = re.compile(r"^```$")


class ErrorGeneracion(RuntimeError):
    """Raised on Anthropic SDK auth/API failures. Never includes the key value."""


# --- Post-processor: fence-strip (pure) + Haiku-judged grounding check ----


def _verificar_resultado_esperado(transcripcion: str, cuerpo: str, cliente) -> bool:
    """Ask Claude Haiku 4.5 whether `cuerpo` is explicitly grounded in
    `transcripcion`, or an invented/generic expectation nobody stated.

    Defaults to True (assume grounded, keep the text) on any failure — a
    broken verifier must never silently erase real analyst-provided
    content. Never raises.
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


def postprocesar_descripcion(texto: str, transcripcion: str, cliente) -> str:
    """Best-effort defense-in-depth over the raw model response: strips a
    whole-output code fence, and — when a "Resultado esperado vs. obtenido"
    section is present — asks Claude Haiku 4.5 itself whether it's grounded
    in `transcripcion`; if not, replaces it with a fixed notice.

    Never raises. Runs OUTSIDE the try/except that maps Anthropic SDK
    failures to `ErrorGeneracion` for the main generation call — a bug here
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
    """Send `transcripcion` (plus retrieved module context, if any) to
    Claude Haiku 4.5.

    `cliente` is injected for testing; when None, `_crear_cliente()` is
    called, which fails fast on a missing/blank `ANTHROPIC_API_KEY` —
    before any context retrieval or network call. That same client is then
    threaded into the default `proveedor_contexto` closure so document
    selection, generation, and verification share one Anthropic client per
    request.

    `proveedor_contexto` is injected for testing; when None, it resolves
    to a closure over `contexto_memoria.buscar_contexto` (a total function
    that never raises and returns `""` on no-match/missing/unreadable
    memory). When it returns a non-empty string, the request uses
    `GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO` and the context-block user
    template. Otherwise the request stays byte-identical to the
    no-context path.

    The raw model response is passed through `postprocesar_descripcion`
    before it is returned (outside the try/except below).
    """
    if cliente is None:
        cliente = _crear_cliente()

    if proveedor_contexto is None:
        from contexto_memoria import buscar_contexto

        def proveedor_contexto(texto):
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
            system=system_prompt,
            messages=[{"role": "user", "content": mensaje_usuario}],
            max_tokens=1024,
        )
    except Exception as exc:
        logger.error(
            "Fallo en la llamada a Claude Haiku 4.5 (modelo=%s): %s: %s",
            modelo, type(exc).__name__, exc,
        )
        raise ErrorGeneracion(
            "No se pudo generar la descripción (fallo de autenticación o de "
            "la API de Anthropic). Ver logs/app.log para el detalle técnico."
        ) from exc

    return postprocesar_descripcion(_texto_de(respuesta), transcripcion, cliente)
