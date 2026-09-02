"""Haiku-based functional enrichment of the finally-selected documentation.

Turns each raw `.md` (written for developers) into a short functional
summary for the analyst-facing prompts, cached by SHA-256 of the raw
content at `cache/documentacion/<hash>.txt`.

TOTAL by contract: `enriquecer_documentos` never raises and always returns
one block per input document, in the input order. Any failure (missing
`ANTHROPIC_API_KEY`, API error, empty response, cache I/O error) degrades
that one document to its verbatim raw content.

CACHE KEY IS CONTENT-ONLY: it does NOT include the prompt text or the model
id. If `ENRIQUECEDOR_DOCUMENTACION` or `MODELO_ENRIQUECEDOR` changes, wipe
`cache/documentacion/` by hand or stale summaries will be served forever.

Prompt text lives in `prompts.py` (see CLAUDE.md "Prompt repository
convention"). Never imports Streamlit.
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from prompts import ENRIQUECEDOR_DOCUMENTACION, ENTRADA_ENRIQUECEDOR_DOCUMENTACION

logger = logging.getLogger(__name__)

MODELO_ENRIQUECEDOR = "claude-haiku-4-5-20251001"
MAX_TOKENS_ENRIQUECIMIENTO = 700
MAX_TRABAJADORES = 3
MAX_REINTENTOS_RATE_LIMIT = 3
# Anthropic's error text has no Groq-style "try again in Xs" to parse, and
# the `retry-after` header was not live-verified — fixed backoff on purpose.
ESPERA_RATE_LIMIT = 5.0
DIRECTORIO_CACHE_POR_DEFECTO = "./cache/documentacion"


class ErrorConfiguracionAnthropic(RuntimeError):
    """ANTHROPIC_API_KEY absent/blank. Non-fatal: callers degrade to raw content.

    Deliberately NOT `generar_descripcion.ErrorConfiguracion`, which is
    documented as GROQ-specific and IS fatal at its call site.
    """


class ErrorEnriquecimiento(RuntimeError):
    """Haiku answered, but with nothing usable."""


# --- Client ---------------------------------------------------------------


def _crear_cliente():
    """Build the Anthropic client, failing fast if the key is not set.

    Mirrors `generar_descripcion._crear_cliente`: env-only, no network call
    before the check, never logs the key value.
    """
    clave = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not clave:
        raise ErrorConfiguracionAnthropic(
            "ANTHROPIC_API_KEY no está configurada; la documentación se usará sin enriquecer."
        )

    from anthropic import Anthropic

    return Anthropic(api_key=clave)


def _crear_mensaje_con_reintento(cliente, **kwargs):
    """`cliente.messages.create(**kwargs)` with 429 retry.

    Same `status_code == 429` shape as the Groq wrapper (verified live,
    anthropic 1.3.0) but a different call surface, so it is a separate
    function rather than a generic one spanning both SDKs.
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


# --- Content-addressed cache ----------------------------------------------


def resolver_directorio_cache(directorio: Optional[str] = None) -> Path:
    """Explicit arg > `CACHE_DOCUMENTACION_DIR` env var > `./cache/documentacion`.

    Mirrors `contexto_memoria.resolver_directorio`. The env var is optional;
    it is not required in `.env`.
    """
    valor = (
        directorio
        if directorio is not None
        else os.environ.get("CACHE_DOCUMENTACION_DIR", "").strip()
    )
    if not valor:
        valor = DIRECTORIO_CACHE_POR_DEFECTO
    return Path(valor)


def _hash_contenido(contenido: str) -> str:
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()


def _leer_cache(raiz: Path, clave: str) -> Optional[str]:
    """Cached summary, or None (miss / unreadable / empty). Never raises."""
    try:
        ruta = raiz / f"{clave}.txt"
        if not ruta.is_file():
            return None
        texto = ruta.read_text(encoding="utf-8")
    except OSError:
        return None
    return texto or None


def _escribir_cache(raiz: Path, clave: str, resumen: str) -> None:
    """Atomic tmp+replace write. Never raises: an unwritable cache only
    means the next request re-enriches."""
    try:
        raiz.mkdir(parents=True, exist_ok=True)
        temporal = raiz / f"{clave}.{os.getpid()}-{threading.get_ident()}.tmp"
        temporal.write_text(resumen, encoding="utf-8")
        temporal.replace(raiz / f"{clave}.txt")
    except OSError as exc:
        logger.warning(
            "No se pudo escribir la caché de enriquecimiento (%s): %s: %s",
            raiz, type(exc).__name__, exc,
        )


# --- Single-document enrichment -------------------------------------------


def _enriquecer_uno(cliente, ruta: str, contenido: str) -> str:
    """One Haiku call. Raises on failure; the caller maps that to raw fallback."""
    respuesta = _crear_mensaje_con_reintento(
        cliente,
        model=MODELO_ENRIQUECEDOR,
        max_tokens=MAX_TOKENS_ENRIQUECIMIENTO,
        temperature=0.0,
        system=ENRIQUECEDOR_DOCUMENTACION,
        messages=[
            {
                "role": "user",
                "content": ENTRADA_ENRIQUECEDOR_DOCUMENTACION.format(
                    ruta=ruta, contenido=contenido
                ),
            }
        ],
    )
    # Anthropic returns a list of content blocks, NOT Groq's
    # `choices[0].message.content` — this is the shape FakeAnthropic must mimic.
    texto = "".join(
        bloque.text for bloque in respuesta.content if getattr(bloque, "type", None) == "text"
    ).strip()
    if not texto:
        raise ErrorEnriquecimiento(f"Respuesta vacía de Haiku para {ruta}")
    return texto


# --- Public: total, order-preserving --------------------------------------


def enriquecer_documentos(
    documentos: list[tuple[str, str]],
    *,
    cliente=None,
    directorio_cache: Optional[str] = None,
) -> list[str]:
    """Return one block per `(ruta, contenido_raw)` pair, same length and order.

    Enriched summary when available, verbatim raw content otherwise. Never
    raises. Only cache misses reach the thread pool; hits are a plain file
    read. Results are placed by index — `as_completed` is deliberately not
    used, because `_ensamblar_contexto` gives earlier blocks budget priority.
    """
    if not documentos:
        return []

    resultados: list[str] = [contenido for _, contenido in documentos]  # raw fallback preloaded
    raiz = resolver_directorio_cache(directorio_cache)
    claves = [_hash_contenido(contenido) for _, contenido in documentos]

    pendientes: list[int] = []
    for i, clave in enumerate(claves):
        en_cache = _leer_cache(raiz, clave)
        if en_cache is not None:
            resultados[i] = en_cache
        else:
            pendientes.append(i)

    if not pendientes:
        return resultados

    if cliente is None:
        try:
            cliente = _crear_cliente()
        except Exception as exc:
            logger.warning(
                "Enriquecimiento omitido, se usa documentación cruda: %s: %s",
                type(exc).__name__, exc,
            )
            return resultados

    with ThreadPoolExecutor(max_workers=min(MAX_TRABAJADORES, len(pendientes))) as pool:
        futuros = {
            i: pool.submit(_enriquecer_uno, cliente, documentos[i][0], documentos[i][1])
            for i in pendientes
        }

    for i, futuro in futuros.items():  # dict order == selection order
        try:
            resumen = futuro.result()
        except Exception as exc:
            logger.warning(
                "Enriquecimiento falló para %s, se usa contenido crudo: %s: %s",
                documentos[i][0], type(exc).__name__, exc,
            )
            continue
        resultados[i] = resumen
        _escribir_cache(raiz, claves[i], resumen)

    return resultados
