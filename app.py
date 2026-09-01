"""Streamlit shell: record/upload audio, transcribe, generate description.

Thin UI layer only — never calls Whisper or Groq directly. Delegates to
`transcribir.py` and `generar_descripcion.py`, and maps their typed
exceptions to `st.error` (no raw tracebacks, no key leakage).
"""

import streamlit as st
from dotenv import load_dotenv

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
st.title("Asistente de Voz para Analistas")

if "transcripcion" not in st.session_state:
    st.session_state.transcripcion = ""
if "descripcion" not in st.session_state:
    st.session_state.descripcion = ""

st.header("1. Graba o sube el audio")

audio_bytes = None

# st.audio_input requires Streamlit >= 1.40. Guard it and always render the
# upload fallback too, per the "Recording control unavailable" scenario.
if hasattr(st, "audio_input"):
    grabacion = st.audio_input("Graba tu descripción del problema")
    if grabacion is not None:
        audio_bytes = grabacion.read()
else:
    st.info(
        "Tu versión de Streamlit no soporta grabación en vivo "
        "(`st.audio_input`). Usa la opción de subir archivo."
    )

archivo_subido = st.file_uploader(
    "O sube un archivo de audio", type=["wav", "mp3", "m4a", "ogg"]
)
if archivo_subido is not None:
    audio_bytes = archivo_subido.read()

if audio_bytes is not None and st.button("Transcribir"):
    progreso = st.progress(0.0)

    def _on_progress(fraccion: float) -> None:
        progreso.progress(fraccion)

    try:
        with st.status("Transcribiendo audio...", expanded=True):
            texto = transcribir_bytes(audio_bytes, on_progress=_on_progress)
        st.session_state.transcripcion = texto
    except ErrorDependenciaAudio as exc:
        st.error(str(exc))
    except ErrorTranscripcion as exc:
        st.error(str(exc))

st.header("2. Revisa y edita la transcripción")
st.session_state.transcripcion = st.text_area(
    "Transcripción (editable)",
    value=st.session_state.transcripcion,
    height=200,
)

st.header("3. Genera la descripción para Jira")
transcripcion_vacia = not st.session_state.transcripcion.strip()
if transcripcion_vacia:
    st.warning("No hay transcripción todavía — grábala o súbela primero.")

if st.button("Generar descripción", disabled=transcripcion_vacia):
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
