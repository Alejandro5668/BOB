# Exploration: Fase 4 — standalone Docker packaging (Dockerfile + docker-compose.yml)

## Current State
BOB is a single-file Streamlit app (`app.py`) delegating to three testable, Streamlit-free domain modules: `transcribir.py` (faster-whisper CPU transcription via PyAV, lazy model singleton), `generar_descripcion.py` (Groq client, lazy-fails on missing `GROQ_API_KEY` only when the button is clicked), `contexto_memoria.py` (read-only `MEMORY_DIR`-rooted retrieval, defaults `./memory`, degrades gracefully). No Dockerfile/compose/nginx exist today. `memory/` at repo root is a dev/test fixture; Fase 2 design intent is that production points `MEMORY_DIR` at a real external folder.

## Affected Areas
- `Dockerfile` (new) — base image, system deps, model bake-in, CMD.
- `docker-compose.yml` (new) — port mapping, env wiring, volumes, healthcheck, isolation.
- `.dockerignore` (new).
- `.env.example` (doc-only edit, add `BOB_HOST_PORT`) — expect the same permission-guardrail friction that blocked automated `.env.example` edits in both Fase 1 and Fase 2; plan as a manual task.
- `README.md` (doc-only edit) — file is UTF-16-encoded on disk; any edit tool must handle/preserve that encoding.

## Investigation Findings
1. **faster-whisper uses CTranslate2, not PyTorch** — much smaller wheels than a "torch-adjacent binaries" assumption would suggest.
2. **PyAV (`av`) decodes audio in-process** (confirmed by the code's own docstring: no shell ffmpeg call). PyAV's manylinux wheels typically bundle FFmpeg's shared libs statically, so `pip install av` on `python:3.11-slim` likely decodes wav/mp3/m4a/ogg without `apt-get install ffmpeg` — but this must be confirmed with an actual build + decode smoke test, not assumed.
3. **Real, documented gotcha**: CTranslate2 wheels commonly dynamically link `libgomp.so.1` (OpenMP), and `libgomp1` is not guaranteed on Debian slim — a known failure mode (`ImportError: libgomp.so.1...`). Recommend adding `libgomp1` explicitly in the Dockerfile.
4. Recommend keeping `ffmpeg` too as cheap insurance until the smoke test proves PyAV alone is sufficient — then it can be dropped to shrink the image.
5. Streamlit's own dependency tree (pandas/pyarrow/altair) is likely the largest contributor to image size, not faster-whisper.

## Model weights: bake vs. runtime download
The "base" Whisper model (int8, CTranslate2 format) is tens of MB, not GB. Runtime download risks: internet access needed from inside the container on first use, and repeated downloads on every container recreate unless a cache volume is added. **Recommendation: bake the model at build time** — trivial size cost, removes a first-run-latency/offline-failure mode.

## docker-compose.yml design
- Isolation: explicit distinctive `name:` (e.g. `bob-asistente-voz`) for legible namespacing. Avoid `network_mode: host`.
- Port: container binds `8501` internally (`--server.address=0.0.0.0` required); host side configurable via `ports: - "${BOB_HOST_PORT:-8501}:8501"`.
- Secrets: `env_file: .env` (matches existing convention, simplest for "just works").
- `memory/`: ship compose defaulting to the image-baked fixture (zero config for first run); document, don't require, a production override `volumes: - ${BOB_MEMORY_DIR:-./memory}:/app/memory:ro` + `MEMORY_DIR=/app/memory`.
- Healthcheck: feasible via Streamlit's `/_stcore/health` endpoint. Since `python:3.11-slim` lacks `curl`, recommend a Python-based healthcheck instead of adding an extra apt package.

## Risks
- Image size likely moderate (rough estimate 800MB–1.3GB) — verify with `docker images` once built.
- `libgomp1` must be added explicitly (known ctranslate2 failure mode on slim bases).
- PyAV's static-FFmpeg-bundling assumption needs a real build+decode smoke test across wav/mp3/m4a/ogg before dropping the `ffmpeg` apt package.
- Confirmed: `GROQ_API_KEY` absence must not block container startup — nothing at import time touches the env var; no startup pre-check should be added in a container entrypoint.
- `.env.example` edits have hit a permission guardrail twice before; expect the same for `BOB_HOST_PORT`.
- Windows Docker Desktop: non-issue for Linux wheel resolution (build happens inside the Linux image); real considerations are a possibly-occupied host port 8501, and minor Windows-path bind-mount quirks for a production `memory/` override.
- No auth in front of Streamlit (explicitly out of scope) — worth one documentation line so it isn't later mistaken for an oversight.

## Ready for Proposal

Yes — scope is well-bounded, no blocking ambiguity. Two open decisions (bake model vs. runtime download; keep vs. drop `ffmpeg`) both have clear recommended defaults for `sdd-propose`/`sdd-design` to carry forward.
