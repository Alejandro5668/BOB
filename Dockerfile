FROM python:3.11-slim

# libgomp1: ctranslate2 dynamically links libgomp.so.1 (absent on slim) -> ImportError.
# ffmpeg:   PyAV decode safety net; drop only after the wav/mp3/m4a/ogg smoke test passes.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgomp1 \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV HF_HOME=/opt/models
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Same constructor call transcribir.py::_cargar_modelo() makes at runtime.
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"

COPY app.py transcribir.py generar_descripcion.py contexto_memoria.py prompts.py ./
COPY memory/ ./memory/

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
