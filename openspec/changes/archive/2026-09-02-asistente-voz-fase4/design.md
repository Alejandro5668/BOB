# Design: Standalone Docker Packaging — Fase 4

## Technical Approach

Three new root-level files (`Dockerfile`, `docker-compose.yml`, `.dockerignore`) plus two
documentation edits. **Zero application-source changes** — no module under `app.py`,
`transcribir.py`, `generar_descripcion.py`, `contexto_memoria.py`, `prompts.py` is touched, so
every behavior guaranteed by `openspec/specs/` holds inside the container by construction
(see `specs/NO_DELTA.md`).

Single-stage build on `python:3.11-slim`. Image size is explicitly **not** a constraint for this
internal tool; the Dockerfile optimizes for legibility and for the one property that matters
operationally: the Whisper `base` model is baked at build time, so the first transcription
performs no network I/O.

## Architecture Decisions

| # | Decision | Choice | Alternatives rejected | Rationale |
|---|---|---|---|---|
| 1 | Model weights | Bake at build via the *exact* runtime call `WhisperModel('base', device='cpu', compute_type='int8')` | Runtime download; named cache volume; `faster_whisper.utils.download_model` | Same call as `transcribir.py::_cargar_modelo()` → identical cache key, no drift. Doubles as a build-time smoke test: a broken `libgomp1`/ctranslate2 fails the *build*, never the analyst's click |
| 2 | `HF_HOME=/opt/models` | Explicit, `HOME`-independent cache path | Rely on default `~/.cache/huggingface` | Bake step and runtime read must resolve the same directory regardless of `HOME`/`USER` |
| 3 | System packages | `libgomp1` + `ffmpeg`, `--no-install-recommends` | slim with no apt layer | `libgomp.so.1` is a documented ctranslate2 `ImportError` on Debian slim. `ffmpeg` is a PyAV safety net, dropped only after the 4-format decode smoke test passes |
| 4 | Build stages | Single stage | Multi-stage wheel-builder | User-confirmed: size is irrelevant for an internal tool; do not over-engineer |
| 5 | Isolation | `name: bob-asistente-voz`, Compose default bridge network | `network_mode: host`; external/shared network | Legible `docker ps` prefixes, zero cross-project bleed |
| 6 | Container name | Rely on the project-name prefix (`bob-asistente-voz-app-1`) | Explicit `container_name:` | The prefix is already distinctive; a fixed `container_name` only adds a collision failure mode |
| 7 | Host port | `"${BOB_HOST_PORT:-8501}:8501"` | Hardcoded `8501:8501` | A native `streamlit run` may already hold 8501. Container side stays 8501 always |
| 8 | Secrets | `env_file` loading the whole `.env`, `required: false` | Per-variable `environment:` passthrough | User-confirmed simplicity over per-variable auditability. `required: false` is the one refinement: plain `env_file: .env` makes `docker compose up` **fail** on a clean machine with no `.env`, which would break a stated success criterion. Needs Compose **v2.24+** |
| 9 | `memory/` | Baked fixture is the default in **all** environments, including production | Fail-loud "still using the fixture" startup check | User-confirmed: zero-config first run; the production `MEMORY_DIR` + `:ro` override is documented, never enforced |
| 10 | Healthcheck | `python -c "urllib.request.urlopen('http://localhost:8501/_stcore/health', ...)"` | `curl`; `wget`; no healthcheck | `python:3.11-slim` ships neither `curl` nor `wget`; the interpreter is already there. `start_period: 40s` covers the Streamlit + pandas/pyarrow import cost |
| 11 | Startup env checks | **None.** No `ENTRYPOINT` script, no key pre-check | Entrypoint validating `GROQ_API_KEY` | Would regress the specified lazy-failure contract (Decision 12) |
| 12 | Streamlit env | `STREAMLIT_SERVER_HEADLESS=true`, `STREAMLIT_BROWSER_GATHER_USAGE_STATS=false` | Defaults | Without headless, Streamlit's first-run e-mail prompt blocks a non-interactive container |
| 13 | Container user | `root` (Docker default) | Dedicated non-root `USER` | Keeps the file simple per the size/complexity guidance; recorded as a residual risk and future option |
| 14 | Auth | None; one explicit README line | nginx + `auth_basic` + TLS | Out of scope this phase; documented so it is not later read as an oversight |

### Decision 12 — `GROQ_API_KEY` absence must not block startup (design confirmation, verified against source)

Verified in this phase by reading the code, not assumed:

- `app.py` imports `generar_descripcion` at module load. That module's import-time work is
  `os`, `re`, `unicodedata`, `typing`, and `prompts` — **no env read, no `groq` import**.
- `from groq import Groq` and `os.environ.get("GROQ_API_KEY", ...)` both live *inside*
  `_crear_cliente()` (`generar_descripcion.py:146-161`), which is reached only from
  `generar_descripcion()`, which is called only from the `st.button("Generar descripción")`
  handler (`app.py:87-99`).
- `load_dotenv()` at `app.py:28` is a silent no-op when no `.env` exists.
- `/_stcore/health` is served by the Streamlit server itself, independent of any user action,
  so the container reports `healthy` with the key absent.

Containerization therefore does not change this behavior. The design constraint is
**negative**: the Dockerfile MUST NOT add an entrypoint script, a startup validation, or an
`ENV GROQ_API_KEY` default; the healthcheck MUST NOT touch generation. Verify must assert this
empirically (see Testing Strategy).

## Data Flow

    docker compose up
        │
        ├─ interpolation: ${BOB_HOST_PORT:-8501}   ← Compose reads ./.env (host side)
        │
        └─ container bob-asistente-voz-app-1
             streamlit run app.py --server.address=0.0.0.0 --server.port=8501
                  │
    host:BOB_HOST_PORT ──→ container:8501 ──→ Streamlit
                  │                              │
                  │                              ├─ transcribir.py ─→ WhisperModel('base')
                  │                              │                    ↑ /opt/models (baked, offline)
                  │                              ├─ contexto_memoria ─→ /app/memory (baked fixture)
                  │                              │                      or MEMORY_DIR (:ro mount)
                  │                              └─ generar_descripcion ─→ api.groq.com (network,
                  │                                                        only on button click)
    healthcheck ──┴─→ python urllib → localhost:8501/_stcore/health

## File Changes

| File | Action | Description |
|---|---|---|
| `Dockerfile` | Create | Single-stage build, apt deps, pip install, baked model, app + fixture copy, CMD |
| `docker-compose.yml` | Create | Project name, service, port, `env_file`, healthcheck, restart policy |
| `.dockerignore` | Create | Build-context exclusions (VCS, secrets, tests, SDD/tooling dirs) |
| `README.md` | Modify | New `## Ejecutar con Docker (Fase 4)` section, inserted after `## Ejecutar`. **File is UTF-16 LE on disk** — the apply phase must read/write with that encoding; a naive UTF-8 write corrupts the whole file. Not solved here |
| `.env.example` | Modify (**MANUAL**) | Add `BOB_HOST_PORT`. Automated edits to this path were blocked in Fase 1, Fase 2, and again during this design phase (a read attempt was denied). Same guardrail applies; plan it as a manual task with exact copy-paste text, do not work around it |
| `app.py`, `transcribir.py`, `generar_descripcion.py`, `contexto_memoria.py`, `prompts.py`, `requirements.txt` | Unchanged | Explicit non-goal |

## Interfaces / Contracts — exact file contents

### `Dockerfile`

```dockerfile
# BOB - Asistente de Voz para Analistas
# Single-stage on purpose: this is an internal tool, image size is not a
# constraint. What matters is that the Whisper model ships inside the image
# so the first transcription never touches the network.
FROM python:3.11-slim

# libgomp1: ctranslate2 (faster-whisper backend) dynamically links
#           libgomp.so.1, which Debian slim does not ship -> ImportError.
# ffmpeg:   safety net for PyAV decoding. Drop it only once the
#           wav/mp3/m4a/ogg smoke test proves the `av` wheel's bundled
#           FFmpeg is sufficient on its own.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgomp1 \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
# Deterministic, HOME-independent weight cache (populated by the bake step
# below and read back at runtime).
ENV HF_HOME=/opt/models
# A container must never hit Streamlit's interactive first-run e-mail prompt.
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Bake the faster-whisper "base" model using the exact same constructor call
# transcribir.py::_cargar_modelo() makes at runtime, so the cache key matches.
# Two guarantees:
#   1. weights live in HF_HOME -> zero download on first click, works offline
#   2. a broken libgomp1/ctranslate2 fails the BUILD, never the analyst
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"

# Application modules (explicit, not `COPY . .`).
COPY app.py transcribir.py generar_descripcion.py contexto_memoria.py prompts.py ./

# The repo's memory/ fixture is the DEFAULT context source in every
# environment, production included. Production overrides it with MEMORY_DIR
# plus a read-only bind mount (documented in README.md) - not enforced here.
COPY memory/ ./memory/

EXPOSE 8501

# --server.address=0.0.0.0 is mandatory: binding loopback inside the container
# makes the published port unreachable from the host.
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
```

### `docker-compose.yml`

```yaml
# BOB - Asistente de Voz para Analistas
# Distinctive project name: every container, network and volume created here
# is prefixed "bob-asistente-voz" and cannot collide with another stack on
# the same machine. Never use network_mode: host.
name: bob-asistente-voz

services:
  app:
    build: .
    image: bob-asistente-voz:latest
    # Host side is configurable (a native `streamlit run` may already hold
    # 8501); the container side is always 8501.
    ports:
      - "${BOB_HOST_PORT:-8501}:8501"
    # Loads the WHOLE .env into the container (GROQ_API_KEY, MEMORY_DIR, ...).
    # required: false keeps `docker compose up` working on a clean machine
    # with no .env at all - the app starts healthy and only "Generar
    # descripcion" reports the missing key. Needs Compose v2.24+.
    env_file:
      - path: .env
        required: false
    # python:3.11-slim ships no curl/wget, so probe Streamlit's health
    # endpoint with the interpreter that is already in the image.
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=5)"
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    restart: unless-stopped
```

`BOB_HOST_PORT` is consumed by Compose at **interpolation** time (host side), read from the
project-directory `.env`. It is also passed into the container by `env_file` and simply ignored
there — harmless, but worth stating so it is not mistaken for a container setting.

### `.dockerignore`

```gitignore
# Keep VCS, secrets, tests and tooling out of the build context.
# This is about not shipping irrelevant or sensitive files, not about size.

# VCS
.git/
.gitignore

# Secrets - never let these reach a build layer
.env
.env.*

# Python dev artifacts
.venv/
venv/
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/

# Tests
tests/

# SDD, docs and agent tooling
openspec/
docs/
.codegraph/
.claude/
.atl/
scripts/
CLAUDE.md
README.md

# Local audio samples
*.wav
*.mp3
*.m4a
*.ogg

# Docker files themselves
Dockerfile
docker-compose.yml
.dockerignore
```

### `.env.example` addition — MANUAL TASK

Exact text to append (do not attempt an automated edit; the same permission guardrail that
blocked Fase 1 and Fase 2 was reconfirmed during this design phase):

```dotenv
# Puerto del host donde se publica la UI cuando se ejecuta con Docker.
# El contenedor siempre escucha en 8501 internamente.
BOB_HOST_PORT=8501
```

### `README.md` section — insert after `## Ejecutar`, before `## Descripción generada (Fase 3)`

> **Apply-phase constraint**: `README.md` is UTF-16 LE encoded. Read it with `utf-16`, write it
> back with `utf-16`, preserving the BOM. Do not "fix" the encoding in this change.

`````markdown
## Ejecutar con Docker (Fase 4)

Requiere Docker Engine / Docker Desktop con Compose v2 (>= 2.24).

```bash
docker compose up --build
```

Abre `http://localhost:8501` (o el puerto que definas en `BOB_HOST_PORT`).
Para parar y limpiar: `docker compose down`.

El modelo `base` de `faster-whisper` viene incluido en la imagen: la primera
transcripción no descarga nada y funciona sin internet. Solo "Generar
descripción" necesita red (API de Groq).

### Variables

| Variable | Dónde actúa | Descripción |
|---|---|---|
| `BOB_HOST_PORT` | Host (`docker-compose.yml`) | Puerto publicado en la máquina. Por defecto `8501`. Cámbialo si ya tienes otro Streamlit ocupando ese puerto. El contenedor siempre escucha en 8501. |
| `GROQ_API_KEY` | Contenedor | Se carga desde `.env`. Si falta, el contenedor arranca igual y queda `healthy`; el error solo aparece al pulsar "Generar descripción". |
| `MEMORY_DIR` | Contenedor | Por defecto usa el `memory/` incluido en la imagen. |

`.env` es opcional: `docker compose up` funciona sin él. Ten en cuenta que
`env_file` carga **todo** el archivo dentro del contenedor, no variable a
variable.

### Usar el `memory/` real en producción

La imagen incluye el `memory/` de ejemplo del repo y lo usa por defecto en
todos los entornos. Para apuntar al `memory/` real de Kawak, monta la carpeta
en modo solo lectura y redirige `MEMORY_DIR`:

```yaml
services:
  app:
    volumes:
      - /ruta/al/memory/real:/mnt/memory:ro
    environment:
      MEMORY_DIR: /mnt/memory
```

El `:ro` añade una garantía a nivel de Docker sobre la disciplina de solo
lectura que ya aplica `contexto_memoria.py`.

### Seguridad

El puerto publicado **no tiene autenticación**: cualquiera con acceso de red a
la máquina puede abrir la UI. Uso previsto: `localhost` o una red interna de
confianza. Un reverse proxy con `auth_basic`/TLS es una opción para una fase
futura, no está incluida aquí.
`````

## Testing Strategy

| Layer | What to test | Approach |
|---|---|---|
| Build | Image builds; model bake succeeds; ctranslate2 loads | `docker compose build`; the bake `RUN` is itself the ctranslate2/`libgomp1` assertion |
| Smoke — decode | wav, mp3, m4a, ogg all transcribe | Upload one file per format through the UI. **Gate for dropping `ffmpeg`**: only after all four pass |
| Smoke — offline | First transcription with no network | `docker network disconnect` (or run with the network detached), then transcribe. Proves the bake |
| Smoke — no key | Container starts and reaches `healthy` with `GROQ_API_KEY` absent; error surfaces only on button click | Run with no `.env`; assert `docker ps` shows `(healthy)`; then click "Generar descripción" and expect the existing `ErrorConfiguracion` message |
| Smoke — no `.env` | `docker compose up` succeeds on a clean checkout | Validates `required: false` |
| Smoke — port | Works with 8501 occupied | Set `BOB_HOST_PORT=8599`, confirm UI on 8599 |
| Smoke — memory | Fixture by default; `:ro` override reads external folder and cannot be written | Run both configurations |
| Isolation | Only `bob-asistente-voz`-prefixed resources; `down` leaves no orphans | `docker ps -a`, `docker network ls`, `docker volume ls` before/after |
| Metric | Record image size | `docker images bob-asistente-voz:latest` → verify report |
| Regression | Host `pytest` still green | Unchanged sources; run `pytest` to confirm no collateral damage |

No new unit tests: this change adds no Python code. All verification is build + runtime smoke.

## Threat Matrix

**N/A** — no routing, VCS/PR automation, executable-file classification, or dynamic
shell/argument composition. The container `CMD` and `healthcheck` are static exec-form
argument vectors with no user-controlled interpolation; no shell is invoked. The matrix rows
(documentation-like paths, git repository selection, commit state, push state, PR commands)
have no counterpart in this change. Container-boundary hygiene is handled by concrete design
elements instead: `.dockerignore` excludes `.env`/`.env.*` from the build context, the
Dockerfile uses explicit `COPY` targets rather than `COPY . .`, and no secret is ever baked
into a layer.

## Migration / Rollout

No migration. Purely additive: three new files, two doc edits, zero source changes, no
persistent state, no schema. The local `streamlit run app.py` workflow is byte-for-byte
unaffected. Rollback = revert the PR; on a machine, `docker compose down` plus deleting the
image leaves nothing behind but cached layers.

## Open Questions

- [ ] Is Compose on the target machines >= 2.24 (required by `env_file: path/required`)? If an
      older Compose is in play, fall back to plain `env_file: .env` and make
      `cp .env.example .env` a documented prerequisite, dropping the "works with no `.env`"
      success criterion. Resolve during the build smoke test.
- [ ] Can `ffmpeg` be dropped? Decided by the 4-format decode smoke test, not in design. If it
      passes, removing it is a separate, optional follow-up — not part of this change.
- [ ] Running as `root` inside the container is accepted for this phase. A non-root `USER`
      (plus a writable `HOME` for Streamlit) is a future hardening option, not built here.
