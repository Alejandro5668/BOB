"""Local CPU audio transcription via faster-whisper.

Owns the whole transcription lifecycle: dependency check, model loading,
temp-file handling, and progress reporting. Never imports Streamlit, so it
stays callable/testable as a standalone module (see spec "Module
Testability").
"""

from __future__ import annotations

import importlib.util
import logging
import os
import tempfile
from typing import Callable, Optional

logger = logging.getLogger(__name__)

ProgresoCallback = Callable[[float], None]


class ErrorDependenciaAudio(RuntimeError):
    """Raised when ffmpeg/av decode support is not available."""


class ErrorTranscripcion(RuntimeError):
    """Raised when audio decode or model inference fails."""


_modelo = None


def verificar_dependencias() -> None:
    """Raise ErrorDependenciaAudio if the `av` package is not importable.

    faster-whisper decodes audio through PyAV bindings (in-process, no
    shell ffmpeg invocation); if `av` is missing, fail with a clear setup
    message instead of a raw stack trace.
    """
    if importlib.util.find_spec("av") is None:
        raise ErrorDependenciaAudio(
            "Falta el paquete 'av' (requerido para decodificar audio). "
            "Instala las dependencias con: pip install -r requirements.txt"
        )


def _cargar_modelo():
    """Lazily construct and cache the WhisperModel singleton."""
    global _modelo
    if _modelo is None:
        from faster_whisper import WhisperModel

        _modelo = WhisperModel("base", device="cpu", compute_type="int8")
    return _modelo


def transcribir_archivo(
    ruta: str,
    *,
    on_progress: Optional[ProgresoCallback] = None,
    idioma: str = "es",
    vad: bool = True,
) -> str:
    """Transcribe the audio file at `ruta` and return the full transcript.

    Iterates faster-whisper's lazy segment generator so `on_progress`
    (0.0..1.0) fires as each segment is actually decoded, giving a real
    progress signal for multi-minute recordings without a worker thread.
    """
    verificar_dependencias()
    modelo = _cargar_modelo()

    try:
        segments, info = modelo.transcribe(
            ruta,
            vad_filter=vad,
            language=idioma,
            beam_size=1,
        )

        texto = []
        duracion = info.duration or 0
        for segment in segments:
            texto.append(segment.text)
            if on_progress is not None and duracion > 0:
                on_progress(min(segment.end / duracion, 1.0))

        if on_progress is not None:
            on_progress(1.0)

        return "".join(texto).strip()
    except ErrorDependenciaAudio:
        raise
    except Exception as exc:
        logger.error("Fallo transcribiendo audio (ruta=%s): %s: %s", ruta, type(exc).__name__, exc)
        raise ErrorTranscripcion(
            f"No se pudo transcribir el audio: {exc}"
        ) from exc


def transcribir_bytes(
    datos: bytes,
    sufijo: str = ".wav",
    *,
    on_progress: Optional[ProgresoCallback] = None,
) -> str:
    """Write `datos` to a temp file, transcribe it, and always clean up.

    The temp file's handle is closed before faster-whisper opens the path
    (Windows forbids reopening a file that is still open elsewhere), and
    the file is unlinked in `finally` regardless of success or failure.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=sufijo, delete=False)
    ruta = tmp.name
    try:
        tmp.write(datos)
        tmp.close()
        return transcribir_archivo(ruta, on_progress=on_progress)
    finally:
        if os.path.exists(ruta):
            os.unlink(ruta)
