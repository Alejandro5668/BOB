"""Streamlit shell: record audio, auto-transcribe, generate description.

Thin UI layer only — never calls Whisper or Groq directly. Delegates to
`transcribir.py` and `generar_descripcion.py`, and maps their typed
exceptions to `st.error` (no raw tracebacks, no key leakage).

Fase 2: also calls `contexto_memoria.diagnosticar()` right before
generation and renders any result via `st.info` — a non-blocking notice,
never `st.error`, since generation proceeds with transcript-only
submission regardless (see design.md "degrade notice" decision).

UI/UX pass: transcription now runs automatically the moment a new
recording is available (no manual "Transcribir" click); file upload is
out of scope for now; `st.audio_input` is used unconditionally since
`requirements.txt` already pins `streamlit>=1.40`.
"""

import streamlit as st
from dotenv import load_dotenv

from logging_config import configurar_logging

configurar_logging()

from contexto_memoria import diagnosticar
from generar_descripcion import (
    ErrorConfiguracion,
    ErrorGeneracion,
    generar_descripcion,
)
from transcribir import (
    ErrorDependenciaAudio,
    ErrorTranscripcion,
    transcribir_bytes,
)

load_dotenv()

st.set_page_config(page_title="Asistente de Voz — Analistas")

# Best-effort size bump for buttons: `stButton` is a `st.button` we render
# ourselves (guaranteed to apply); `stAudioInput` targets Streamlit's own
# recorder widget via its documented data-testid — bigger controls if
# Streamlit's internal markup matches, a harmless no-op if it doesn't.
st.markdown(
    """
    <style>
    div[data-testid="stButton"] button {
        font-size: 1.15rem;
        padding: 0.75rem 1.5rem;
    }
    div[data-testid="stAudioInput"] button {
        transform: scale(1.2);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Asistente de Voz para Analistas")

if "transcripcion" not in st.session_state:
    st.session_state.transcripcion = ""
if "descripcion" not in st.session_state:
    st.session_state.descripcion = ""
if "ultimo_audio_id" not in st.session_state:
    st.session_state.ultimo_audio_id = None

st.header("1. Grabá tu audio")
grabacion = st.audio_input("Grabá tu descripción del problema")

if grabacion is not None and grabacion.file_id != st.session_state.ultimo_audio_id:
    st.session_state.ultimo_audio_id = grabacion.file_id
    progreso = st.progress(0.0)

    def _on_progress(fraccion: float) -> None:
        progreso.progress(fraccion)

    try:
        with st.status("Transcribiendo audio...", expanded=True):
            texto = transcribir_bytes(grabacion.read(), on_progress=_on_progress)
        st.session_state.transcripcion = texto
    except ErrorDependenciaAudio as exc:
        st.error(str(exc))
    except ErrorTranscripcion as exc:
        st.error(str(exc))

st.header("2. Revisá la transcripción y generá la descripción")
st.session_state.transcripcion = st.text_area(
    "Transcripción (editable)",
    value=st.session_state.transcripcion,
    height=200,
)

transcripcion_vacia = not st.session_state.transcripcion.strip()
if transcripcion_vacia:
    st.warning("No hay transcripción todavía — grabá tu audio primero.")

if st.button(
    "Generar descripción",
    disabled=transcripcion_vacia,
    type="primary",
    use_container_width=True,
):
    aviso_memoria = diagnosticar()
    if aviso_memoria:
        st.info(aviso_memoria)
    try:
        with st.spinner("Generando descripción..."):
            st.session_state.descripcion = generar_descripcion(
                st.session_state.transcripcion
            )
    except ErrorConfiguracion as exc:
        st.error(str(exc))
    except ErrorGeneracion as exc:
        st.error(str(exc))

st.session_state.descripcion = st.text_area(
    "Descripción para Jira (editable, copia y pega)",
    value=st.session_state.descripcion,
    height=200,
)
