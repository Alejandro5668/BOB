# Proposal: Standalone Docker Packaging — Fase 4

## Intent

BOB today only runs from a manual local setup (Python 3.11 + venv + `pip install -r requirements.txt` + `streamlit run`), so every new analyst machine repeats an error-prone install and the first transcription silently downloads model weights from the network. Fase 4 makes the app reproducible and portable: `docker compose up` starts a working BOB, with no host Python, no first-run download, and no interference with unrelated containers already on the machine.

## Scope

### In Scope
- `Dockerfile`: `python:3.11-slim` base, `libgomp1` + `ffmpeg` apt deps, `pip install -r requirements.txt`, Whisper `base` (int8/CTranslate2) model **baked at build time**, `COPY memory/` fixture, `CMD streamlit run app.py --server.port=8501 --server.address=0.0.0.0`.
- `docker-compose.yml`: distinctive project `name: bob-asistente-voz`, default per-project bridge network, `ports: "${BOB_HOST_PORT:-8501}:8501"`, `env_file: .env`, Python-based healthcheck against `/_stcore/health`, `restart: unless-stopped`.
- `.dockerignore` (`.venv/`, `__pycache__/`, `.git/`, `.pytest_cache/`, `tests/`, `*.wav`).
- `README.md` Docker section: run, `BOB_HOST_PORT`, documented production `MEMORY_DIR` read-only bind-mount override, one line noting the app is unauthenticated.
- `.env.example`: add `BOB_HOST_PORT` (**manual task** — automated edits to this file were blocked in Fase 1 and Fase 2).
- Build + decode smoke test across wav/mp3/m4a/ogg; record image size.

### Out of Scope
- nginx reverse proxy, TLS, `auth_basic` / any authentication (documented future option, not built).
- mysql or any external service, external/shared Docker networks, integration into another project's compose stack.
- GPU/CUDA images, multi-arch publishing, registry push, CI build pipeline.
- Any change to `app.py`, `transcribir.py`, `generar_descripcion.py`, `contexto_memoria.py`, `prompts.py`, or `requirements.txt`.
- Kubernetes/Swarm manifests; Fase 5 (history, reindex, model tuning).

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- None.

**No spec delta is needed.** This change is packaging/deployment only: it adds no product-facing behavior and modifies no requirement. The container MUST preserve existing spec behavior byte-for-byte — notably `jira-description-generation` "fail fast on missing `GROQ_API_KEY`" (lazy, on button click only) and `context-retrieval` "`MEMORY_DIR` unset degrades to a non-blocking notice". Fase 4 is a **design + tasks** change; `sdd-spec` should record "no delta" rather than invent a `deployment` capability.

## Approach

Single-stage Dockerfile, exploration's recommended defaults. Key decisions:

| Decision | Choice | Rationale |
|---|---|---|
| Model weights | Bake at build time | `base` int8 is tens of MB — trivial next to Streamlit's own tree; removes first-run latency and the offline/VPN failure mode; no cache volume needed |
| `libgomp1` | Always install | CTranslate2 wheels dynamically link `libgomp.so.1`; known `ImportError` on Debian slim |
| `ffmpeg` | Install now, drop only if smoke test proves PyAV's bundled FFmpeg decodes all 4 formats | ~30–60MB buys out a residual assumption about PyAV wheel bundling |
| Isolation | Explicit `name:`, default private bridge network, never `network_mode: host` | Legible names in `docker ps`; zero cross-project bleed |
| Host port | `${BOB_HOST_PORT:-8501}` | A native `streamlit run` may already hold 8501 on a dev machine |
| Secrets | `env_file: .env` | Matches existing `.env.example` convention; documented that it loads the whole file |
| `memory/` | Default = image-baked fixture; production override documented, not required | `docker compose up` works with zero config; `:ro` mount adds Docker-level enforcement over Fase 2's code-level read-only discipline |
| Healthcheck | `python -c "urllib.request.urlopen(...)"` | `python:3.11-slim` has no `curl`; avoids an apt package for one probe |
| Startup env checks | None | Adding a `GROQ_API_KEY` entrypoint pre-check would regress documented lazy-failure behavior |

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `Dockerfile` | New | Build recipe with baked model |
| `docker-compose.yml` | New | Service, port, env, healthcheck, isolation |
| `.dockerignore` | New | Build-context exclusions |
| `README.md` | Modified | Docker section (file is UTF-16 on disk — preserve encoding) |
| `.env.example` | Modified (manual) | `BOB_HOST_PORT` |
| Application modules | Unchanged | No source changes at all |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| PyAV bundled FFmpeg insufficient for some format | Med | Keep `ffmpeg` apt package until the 4-format smoke test passes |
| Image larger than expected (est. 800MB–1.3GB) | Med | Measure with `docker images`; `.dockerignore` + `--no-install-recommends`; accept (Streamlit tree dominates) |
| Build-time model download fails (no/blocked internet at build) | Low | Build fails loudly and early, never at analyst runtime; documented as a build prerequisite |
| Host port 8501 already taken | Med | `BOB_HOST_PORT` documented in README and `.env.example` |
| Automated `.env.example` edit blocked again | High | Planned as an explicit manual task with the exact line to add |
| Unauthenticated port on a shared machine | Med | Accepted for this phase; one explicit README line so it is not later read as an oversight |
| Windows bind-mount permission quirks for prod `memory/` override | Low | Read-only mounts are unaffected; documented |

## Rollback Plan

Purely additive: three new files plus two documentation edits, zero application-source changes. Revert the single PR — the local `streamlit run app.py` workflow is byte-for-byte unaffected because no existing module is touched. No data, schema, migration, or persistent deploy state exists. Partial rollback: `docker compose down` and delete the image; nothing on the host is left behind except the built image layers.

## Dependencies

- Docker Engine / Docker Desktop with Compose v2 on the target machine.
- Outbound internet **at build time only** (PyPI + Hugging Face for the baked model). Runtime internet is needed only for Groq calls during "Generar descripción".
- Fases 1–3 merged and unchanged; `requirements.txt` is the source of truth for Python deps.

## Success Criteria

- [ ] `docker compose up` on a clean machine with no `.env` serves a working UI at `http://localhost:8501` (or `BOB_HOST_PORT`).
- [ ] Transcription of wav/mp3/m4a/ogg succeeds on first click with the container network disconnected (proves the model is baked and PyAV/ffmpeg decode works).
- [ ] Container starts and stays healthy with `GROQ_API_KEY` absent; only clicking "Generar descripción" surfaces the existing configuration error.
- [ ] With `MEMORY_DIR` unset, context retrieval uses the baked fixture; with the documented `:ro` override, it reads the external folder and cannot write to it.
- [ ] `docker compose up` while another project holds port 8501 works after setting `BOB_HOST_PORT`, and creates no shared/external network — `docker ps`/`docker network ls` show only `bob-asistente-voz`-prefixed resources.
- [ ] `docker compose down` leaves no orphan containers, networks, or volumes.
- [ ] Compose healthcheck reports `healthy`; measured image size recorded in the verify report.
