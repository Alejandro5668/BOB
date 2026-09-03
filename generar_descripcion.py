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

# --- Post-processor: headings + fixed notices ----------------------------

ENCABEZADO_MODULO = "## Módulo afectado"
MODULO_NO_IDENTIFICADO = "Módulo afectado: no identificado"

ENCABEZADO_RESULTADO = "## Resultado esperado vs. obtenido"
AVISO_RESULTADO_NO_CONFIABLE = (
    "Resultado esperado vs. obtenido: no se pudo determinar de forma confiable"
)

_PATRON_FENCE_INICIO = re.compile(r"^```[a-zA-Z]*$")
_PATRON_FENCE_FIN = re.compile(r"^```$")


class ErrorGeneracion(RuntimeError):
    """Raised on Anthropic SDK auth/API failures. Never includes the key value."""


# --- Post-processor: section location/replacement (pure) ------------------


def _ubicar_seccion(lineas: list[str], encabezado: str) -> Optional[tuple[int, int]]:
    """Find `encabezado` in `lineas`; return (heading_index, body_end_index),
    where body_end_index is the next `## `-heading line or len(lineas) if
    this is the last section. None if `encabezado` isn't present."""
    indice = None
    for i, linea in enumerate(lineas):
        if linea.strip().rstrip(":") == encabezado:
            indice = i
            break
    if indice is None:
        return None

    fin = len(lineas)
    for j in range(indice + 1, len(lineas)):
        if lineas[j].startswith("## "):
            fin = j
            break
    return indice, fin


def _reemplazar_cuerpo(lineas: list[str], indice_encabezado: int, fin_cuerpo: int, nuevo_cuerpo: str) -> list[str]:
    """Replace the body between `indice_encabezado` and `fin_cuerpo` with
    `nuevo_cuerpo` (a single fixed-notice line), preserving a blank
    separator line before whatever section (if any) comes after."""
    reemplazo = [nuevo_cuerpo]
    if fin_cuerpo < len(lineas):
        reemplazo.append("")
    return lineas[: indice_encabezado + 1] + reemplazo + lineas[fin_cuerpo:]


# --- Post-processor: Haiku-judged grounding checks -------------------------


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


def _verificar_modulo_afectado(fuente: str, modulo: str, cliente) -> bool:
    """Ask Claude Haiku 4.5 whether `modulo` is a literal quote (module/
    screen/functionality name) from `fuente` (transcript + retrieved
    context), or an invented/paraphrased name nobody actually used.

    Defaults to True (assume grounded, keep the text) on any failure — same
    fail-open policy as `_verificar_resultado_esperado`. Never raises.
    """
    from prompts import ENTRADA_VERIFICADOR_MODULO_AFECTADO, VERIFICADOR_MODULO_AFECTADO

    try:
        datos = _pedir_json(
            cliente,
            model=MODELO_AUXILIAR,
            system=VERIFICADOR_MODULO_AFECTADO,
            mensaje_usuario=ENTRADA_VERIFICADOR_MODULO_AFECTADO.format(fuente=fuente, modulo=modulo),
            max_tokens=150,
        )
        return bool(datos.get("fundamentado", True))
    except Exception as exc:
        logger.warning(
            "Verificación de 'Módulo afectado' falló, se conserva el texto: %s: %s",
            type(exc).__name__, exc,
        )
        return True


def postprocesar_descripcion(texto: str, transcripcion: str, cliente, contexto: str = "") -> str:
    """Best-effort defense-in-depth over the raw model response: strips a
    whole-output code fence; when `contexto` was retrieved, asks Claude
    Haiku 4.5 whether the cited `## Módulo afectado` name is a literal quote
    from the transcript+context (if not, falls back to
    `MODULO_NO_IDENTIFICADO`); and — when a "Resultado esperado vs. obtenido"
    section is present — asks whether it's grounded in `transcripcion` (if
    not, replaces it with a fixed notice).

    The módulo check only runs when `contexto` is non-empty: without
    retrieved context the model has only the transcript's own wording to
    draw from (rule 6 already covers that at the prompt level), and this is
    exactly the scenario that caused a real invented name ("edición masiva
    de documentos" replacing the analyst's own "listado único de
    documentos") to slip through despite the prompt rule.

    Never raises. Runs OUTSIDE the try/except that maps Anthropic SDK
    failures to `ErrorGeneracion` for the main generation call — a bug here
    (including a verifier call itself failing) degrades to keeping the
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

    if contexto:
        ubicacion_modulo = _ubicar_seccion(lineas, ENCABEZADO_MODULO)
        if ubicacion_modulo is not None:
            i_modulo, fin_modulo = ubicacion_modulo
            cuerpo_modulo = "\n".join(lineas[i_modulo + 1 : fin_modulo]).strip()
            if cuerpo_modulo and cuerpo_modulo != MODULO_NO_IDENTIFICADO:
                fuente = f"{transcripcion}\n{contexto}"
                if not _verificar_modulo_afectado(fuente, cuerpo_modulo, cliente):
                    lineas = _reemplazar_cuerpo(lineas, i_modulo, fin_modulo, MODULO_NO_IDENTIFICADO)
                    resultado = "\n".join(lineas)

    ubicacion_resultado = _ubicar_seccion(lineas, ENCABEZADO_RESULTADO)
    if ubicacion_resultado is None:
        return resultado

    indice_encabezado, fin_cuerpo = ubicacion_resultado
    cuerpo = "\n".join(lineas[indice_encabezado + 1 : fin_cuerpo]).strip()

    if cuerpo and _verificar_resultado_esperado(transcripcion, cuerpo, cliente):
        return resultado

    lineas = _reemplazar_cuerpo(lineas, indice_encabezado, fin_cuerpo, AVISO_RESULTADO_NO_CONFIABLE)
    return "\n".join(lineas)


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

    return postprocesar_descripcion(_texto_de(respuesta), transcripcion, cliente, contexto)
