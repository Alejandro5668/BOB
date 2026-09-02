"""Shared Anthropic client scaffolding — Claude Haiku 4.5 for every LLM
call site in this project (ticket generation, documentation Q&A, and
document selection for context retrieval).

Owns client construction, 429-retry, and the two response-shape helpers
every call site needs: `_texto_de` (plain text out of a response) and
`_pedir_json` (a JSON-mode replacement built on an assistant-role prefill
of `"{"` plus `json.JSONDecoder().raw_decode`, since the Anthropic
Messages API has no `response_format` parameter equivalent to Groq's JSON
mode).

`ErrorConfiguracion` is the ONE missing/blank `ANTHROPIC_API_KEY` error for
the whole project. Whether it is fatal is a CALL-SITE policy, not baked in
here: `generar_descripcion.generar_descripcion` and
`consultar_documentacion.responder_consulta` let it propagate (fail-fast —
no key means no call); `contexto_memoria.buscar_contexto` and the
"Resultado esperado" verifier (`generar_descripcion._verificar_resultado_esperado`)
catch it and degrade instead.

Never imports Streamlit.
"""

from __future__ import annotations

import json
import logging
import os
import time

logger = logging.getLogger(__name__)

MODELO_HAIKU = "claude-haiku-4-5-20251001"
MAX_REINTENTOS_RATE_LIMIT = 3
# Anthropic's error text has no Groq-style "try again in Xs" to parse, and
# the `retry-after` header was not live-verified — fixed backoff on purpose.
ESPERA_RATE_LIMIT = 5.0


class ErrorConfiguracion(RuntimeError):
    """`ANTHROPIC_API_KEY` absent/blank. Fatality is a call-site policy:
    some callers let this propagate (fail-fast), others catch it and
    degrade — see the module docstring above."""


def _crear_cliente():
    """Build the Anthropic client, failing fast if the key is not set.

    Reads `ANTHROPIC_API_KEY` only from the environment. Raises
    `ErrorConfiguracion` before any network call if the value is absent or
    blank. Never logs the key value.
    """
    clave = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not clave:
        raise ErrorConfiguracion(
            "ANTHROPIC_API_KEY no está configurada. Debe definirse la variable de "
            "entorno (ver .env.example) antes de continuar."
        )

    from anthropic import Anthropic

    return Anthropic(api_key=clave)


def _crear_mensaje_con_reintento(cliente, **kwargs):
    """`cliente.messages.create(**kwargs)` with 429 retry.

    `status_code == 429` shape verified live against anthropic 1.3.0.
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
    """Join every text content block in an Anthropic Messages response.

    Anthropic returns a list of content blocks, NOT Groq's
    `choices[0].message.content` string — this is the shape every
    `FakeAnthropic` test fixture in this project must mimic.
    """
    return "".join(
        bloque.text for bloque in respuesta.content if getattr(bloque, "type", None) == "text"
    ).strip()


def _pedir_json(cliente, *, model, system, mensaje_usuario, max_tokens) -> dict:
    """Ask for a JSON object using an assistant-role prefill of `"{"`
    instead of Groq's `response_format={"type": "json_object"}` (no
    equivalent parameter exists on the Messages API).

    Parses with `json.JSONDecoder().raw_decode`, NOT `json.loads` — the
    prefill makes a leading code fence or preamble structurally
    impossible, but trailing prose after the closing `}` must not blow
    away an otherwise-good parse.
    """
    respuesta = _crear_mensaje_con_reintento(
        cliente,
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[
            {"role": "user", "content": mensaje_usuario},
            {"role": "assistant", "content": "{"},
        ],
    )
    texto_completo = "{" + _texto_de(respuesta)
    datos, _ = json.JSONDecoder().raw_decode(texto_completo)
    return datos
