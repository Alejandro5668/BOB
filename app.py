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
Known module names/aliases are passed as `keyterms` to bias recognition
toward domain vocabulary (e.g. "gestión de riesgos").

Visual pass: navy/teal gradient palette + Sora font, inspired by (not a
pixel-perfect clone of) dapta.ai's landing page — purely cosmetic, no
functional/state changes below the CSS block.
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

st.set_page_config(page_title="BOB — Contame el problema", page_icon="🎙️")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Sora', sans-serif;
    }

    div[data-testid="stAppViewContainer"] {
        background: linear-gradient(180deg, #F4F8FB 0%, #FFFFFF 45%);
    }

    .bob-hero {
        display: flex;
        align-items: center;
        gap: 0.9rem;
        margin-bottom: 0.25rem;
    }
    .bob-hero-badge {
        font-size: 2.2rem;
        line-height: 1;
    }
    .bob-hero-title {
        font-weight: 800;
        font-size: 2.1rem;
        background: linear-gradient(90deg, #0B1E3F 0%, #0E7C86 60%, #14B8A6 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 0;
    }
    .bob-hero-tagline {
        color: #4A5568;
        font-size: 1.05rem;
        margin: 0.1rem 0 1.6rem 0;
    }

    .bob-step-card {
        background: #FFFFFF;
        border: 1px solid #E3ECF2;
        border-radius: 16px;
        padding: 1.1rem 1.4rem 0.4rem 1.4rem;
        margin-bottom: 1.2rem;
        box-shadow: 0 4px 18px rgba(11, 30, 63, 0.05);
    }
    .bob-step-title {
        font-weight: 700;
        font-size: 1.15rem;
        color: #0B1E3F;
        margin-bottom: 0.15rem;
    }
    .bob-step-subtitle {
        color: #6B7C8E;
        font-size: 0.92rem;
        margin-bottom: 0.7rem;
    }

    div[data-testid="stButton"] button {
        font-size: 1.15rem;
        font-weight: 700;
        padding: 0.75rem 1.5rem;
        border-radius: 12px;
    }
    div[data-testid="stButton"] button[kind="primary"] {
        background: linear-gradient(90deg, #0E7C86 0%, #14B8A6 100%);
        border: none;
    }
    div[data-testid="stButton"] button[kind="primary"]:hover {
        background: linear-gradient(90deg, #0B6870 0%, #10A090 100%);
    }
    div[data-testid="stAudioInput"] button {
        transform: scale(1.2);
    }
    div[data-testid="stAudioInput"] {
        border-radius: 12px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="bob-hero">
        <div class="bob-hero-badge">🎙️</div>
        <p class="bob-hero-title">BOB escucha el problema</p>
    </div>
    <p class="bob-hero-tagline">
        Contame lo que te dijo el cliente — yo transcribo, busco el módulo
        involucrado y te dejo la descripción lista para pegar en Jira.
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
    <div class="bob-step-card">
        <div class="bob-step-title">🎤 Dale, contame</div>
        <div class="bob-step-subtitle">
            Grabá la descripción del problema tal como te la contó el cliente.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
grabacion = st.audio_input("Grabación", label_visibility="collapsed")

if grabacion is not None and grabacion.file_id != st.session_state.ultimo_audio_id:
    st.session_state.ultimo_audio_id = grabacion.file_id
    try:
        with st.status("Escuchando con atención...", expanded=True):
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
    <div class="bob-step-card">
        <div class="bob-step-title">📝 ¿Quedó bien?</div>
        <div class="bob-step-subtitle">
            Revisá y corregí lo que haga falta antes de armar el ticket.
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
    st.warning("Todavía no grabaste nada — dale al micrófono cuando quieras.")

if st.button(
    "✨ Armar la descripción",
    disabled=transcripcion_vacia,
    type="primary",
    use_container_width=True,
):
    aviso_memoria = diagnosticar()
    if aviso_memoria:
        st.info(aviso_memoria)
    try:
        with st.spinner("Armando la descripción..."):
            st.session_state.descripcion = generar_descripcion(
                st.session_state.transcripcion
            )
    except ErrorConfiguracion as exc:
        st.error(str(exc))
    except ErrorGeneracion as exc:
        st.error(str(exc))

st.markdown(
    """
    <div class="bob-step-card">
        <div class="bob-step-title">🚀 Lista para Jira</div>
        <div class="bob-step-subtitle">
            Copiala y pegala en el ticket. También podés retocarla acá.
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
