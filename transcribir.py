"""Audio transcription via the ElevenLabs Speech-to-Text API.

Owns the ElevenLabs client lifecycle. The client is always
constructor-injected (never built at import time) so unit tests run
today with a fake client and a missing `ELEVENLABS_API_KEY` never breaks
import or testing. Never imports Streamlit (see spec "Module
Testability").

Audio now leaves this machine (sent to ElevenLabs) — a deliberate
architecture change from Fase 1's local-only faster-whisper, made at the
user's explicit request. See CLAUDE.md for the recorded decision.
"""

from __future__ import annotations

import logging
import os
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

MODELO = "scribe_v2"


class ErrorConfiguracionAudio(RuntimeError):
    """Raised when ELEVENLABS_API_KEY is absent/blank — before any HTTP call."""


class ErrorTranscripcion(RuntimeError):
    """Raised when the ElevenLabs API call fails."""


def _crear_cliente():
    """Build the ElevenLabs client, failing fast if the API key is not set.

    Reads ELEVENLABS_API_KEY only from the environment. Raises
    ErrorConfiguracionAudio before any network call if the value is
    absent or blank.
    """
    clave = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not clave:
        logger.warning("ELEVENLABS_API_KEY ausente o vacía al intentar transcribir audio.")
        raise ErrorConfiguracionAudio(
            "ELEVENLABS_API_KEY no está configurada. Debe definirse la variable de "
            "entorno (ver .env.example) antes de registrar audio."
        )

    from elevenlabs import ElevenLabs

    return ElevenLabs(api_key=clave)


def transcribir_bytes(
    datos: bytes,
    *,
    cliente=None,
    modelo: str = MODELO,
    idioma: str = "spa",
    keyterms: Optional[Iterable[str]] = None,
) -> str:
    """Send `datos` (raw audio bytes) to ElevenLabs and return the transcript.

    `cliente` is injected for testing; when None, `_crear_cliente()` is
    called, which fails fast on a missing/blank ELEVENLABS_API_KEY.
    `keyterms` biases recognition toward known vocabulary (e.g. module
    names from `contexto_memoria.nombres_conocidos()`) — capped at
    ElevenLabs' documented limit of 1000 terms.
    """
    if cliente is None:
        cliente = _crear_cliente()

    kwargs = {"model_id": modelo, "language_code": idioma}
    if keyterms:
        kwargs["keyterms"] = list(keyterms)[:1000]

    try:
        resultado = cliente.speech_to_text.convert(file=datos, **kwargs)
    except Exception as exc:
        logger.error(
            "Fallo en la llamada a ElevenLabs (modelo=%s): %s: %s",
            modelo, type(exc).__name__, exc,
        )
        raise ErrorTranscripcion(
            "No se pudo transcribir el audio (fallo de autenticación o de "
            "la API de ElevenLabs). Ver logs/app.log para el detalle técnico."
        ) from exc

    return resultado.text
