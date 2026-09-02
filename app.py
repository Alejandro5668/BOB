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

Transcription now calls the ElevenLabs API (see CLAUDE.md "Transcription
provider" decision) instead of local faster-whisper — a single blocking
call, not a segment-by-segment stream, so there's no per-percentage
progress to show; `st.status(...)` communicates "still working" instead.
Known document/folder names are passed as `keyterms` to bias recognition
toward domain vocabulary.

Visual pass: dark background + lime accent (see `.streamlit/config.toml`)
and Inter typography, following a reference design the user provided.
All copy is neutral Spanish (no voseo, no regionalisms) with no
decorative/generic icons — purely cosmetic, no functional/state changes
below the CSS block.
"""

import streamlit as st
from dotenv import load_dotenv

from logging_config import configurar_logging

configurar_logging()

from contexto_memoria import diagnosticar, nombres_conocidos
from generar_descripcion import (
    ErrorConfiguracion,
    ErrorGeneracion,
    generar_descripcion,
)
from transcribir import (
    ErrorConfiguracionAudio,
    ErrorTranscripcion,
    transcribir_bytes,
)

load_dotenv()

st.set_page_config(page_title="BOB")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700;800;900&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    .bob-eyebrow {
        color: #C6F135;
        font-weight: 700;
        font-size: 0.8rem;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        margin-bottom: 0.4rem;
    }
    .bob-title {
        font-weight: 900;
        font-size: 2.4rem;
        line-height: 1.15;
        color: #FFFFFF;
        margin: 0 0 0.9rem 0;
    }
    .bob-title-accent {
        color: #C6F135;
    }
    .bob-subtitle {
        color: #9CA3AF;
        font-size: 1.02rem;
        line-height: 1.5;
        margin-bottom: 1.8rem;
        max-width: 44rem;
    }

    .bob-card {
        background: #18181A;
        border: 1px solid #2A2A2C;
        border-radius: 14px;
        padding: 1.1rem 1.4rem 0.4rem 1.4rem;
        margin-bottom: 1.1rem;
    }
    .bob-card-title {
        font-weight: 800;
        font-size: 1.1rem;
        color: #FFFFFF;
        margin-bottom: 0.15rem;
    }
    .bob-card-subtitle {
        color: #9CA3AF;
        font-size: 0.9rem;
        margin-bottom: 0.7rem;
    }

    div[data-testid="stButton"] button {
        font-weight: 800;
        font-size: 1.05rem;
        padding: 0.7rem 1.5rem;
        border-radius: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <p class="bob-eyebrow">Asistente de voz para analistas</p>
    <p class="bob-title">Del audio a la descripción,
        <span class="bob-title-accent">lista para Jira</span></p>
    <p class="bob-subtitle">
        El audio se transcribe, se identifica el módulo afectado y se
        redacta una descripción clara del problema, sin necesidad de
        escribir el ticket de forma manual.
    </p>
    """,
    unsafe_allow_html=True,
)

if "transcripcion" not in st.session_state:
    st.session_state.transcripcion = ""
if "descripcion" not in st.session_state:
    st.session_state.descripcion = ""
if "ultimo_audio_id" not in st.session_state:
    st.session_state.ultimo_audio_id = None

st.markdown(
    """
    <div class="bob-card">
        <div class="bob-card-title">Grabación de audio</div>
        <div class="bob-card-subtitle">
            La transcripción se genera automáticamente al finalizar la grabación.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
grabacion = st.audio_input("Grabación", label_visibility="collapsed")

if grabacion is not None and grabacion.file_id != st.session_state.ultimo_audio_id:
    st.session_state.ultimo_audio_id = grabacion.file_id
    try:
        with st.status("Procesando el audio...", expanded=True):
            texto = transcribir_bytes(
                grabacion.read(), keyterms=nombres_conocidos()
            )
        st.session_state.transcripcion = texto
    except ErrorConfiguracionAudio as exc:
        st.error(str(exc))
    except ErrorTranscripcion as exc:
        st.error(str(exc))

st.markdown(
    """
    <div class="bob-card">
        <div class="bob-card-title">Transcripción</div>
        <div class="bob-card-subtitle">
            El texto puede corregirse antes de generar la descripción.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.session_state.transcripcion = st.text_area(
    "Transcripción",
    value=st.session_state.transcripcion,
    height=200,
    label_visibility="collapsed",
)

transcripcion_vacia = not st.session_state.transcripcion.strip()
if transcripcion_vacia:
    st.warning("Aún no se ha registrado ningún audio.")

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
        with st.spinner("Generando la descripción..."):
            st.session_state.descripcion = generar_descripcion(
                st.session_state.transcripcion
            )
    except ErrorConfiguracion as exc:
        st.error(str(exc))
    except ErrorGeneracion as exc:
        st.error(str(exc))

st.markdown(
    """
    <div class="bob-card">
        <div class="bob-card-title">Descripción para Jira</div>
        <div class="bob-card-subtitle">
            El texto puede editarse antes de copiarlo al ticket.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.session_state.descripcion = st.text_area(
    "Descripción",
    value=st.session_state.descripcion,
    height=200,
    label_visibility="collapsed",
)
