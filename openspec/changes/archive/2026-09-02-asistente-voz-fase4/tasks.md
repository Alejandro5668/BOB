# Tasks: Standalone Docker Packaging — Fase 4

Full decisions/exact file contents: `openspec/changes/asistente-voz-fase4/design.md`.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~120-150 (3 new small files + 1 README section; `.env.example` is manual, out-of-diff) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | single-pr |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Docker packaging (all files below) | PR 1 | `docker compose config` | `docker compose build && docker compose up -d` + Phase 3 smoke test | Revert PR; `docker compose down` + delete image; zero app-source impact |

Note: single-pr strategy needs an explicit `size:exception` acceptance recorded before merge, even though estimate is under budget.

## Phase 1: File Creation

- [x] 1.1 Create `Dockerfile` (root) — exact content per design.md: `python:3.11-slim`, `libgomp1`+`ffmpeg`, `HF_HOME=/opt/models` + Streamlit headless envs, `pip install -r requirements.txt`, bake `WhisperModel('base', device='cpu', compute_type='int8')`, explicit `COPY` (no `COPY . .`), `EXPOSE 8501`, `CMD streamlit run ...`.
- [x] 1.2 Create `docker-compose.yml` (root) — exact content per design.md: `name: bob-asistente-voz`, `ports: ["${BOB_HOST_PORT:-8501}:8501"]`, `env_file: [{path: .env, required: false}]` (map form — required for "no `.env`" success criterion, not the bare-string form), Python `urllib` healthcheck, `restart: unless-stopped`.
- [x] 1.3 Create `.dockerignore` (root) — exact exclusion list per design.md (`.git/`, `.env*`, caches, `tests/`, `openspec/`, audio fixtures, Docker files themselves).

## Phase 2: Documentation

- [ ] 2.1 **MANUAL STEP — do not automate.** Add `BOB_HOST_PORT=8501` (+ 2 comment lines, exact text in design.md) to `.env.example`. Same guardrail as Fase 1/2/3: automated edits are blocked (read denied); human applies outside the agent's write path. **BLOCKED** — hard-deny on `.env*` paths confirmed again this phase (`Bash cat .env.example` denied by permission guardrail). Requires manual application outside the agent's write path.
- [x] 2.2 **ENCODING WARNING** — `README.md` is UTF-16LE on disk with BOM. Verify encoding before editing; read/write preserving UTF-16LE. A UTF-8 write corrupts the file. Verified via `xxd`: file is UTF-16LE **without** a BOM (first bytes `23 00` = `#`, no `FF FE` marker) — design.md's "with BOM" note does not match the actual bytes on disk; edit performed via `iconv` UTF-16LE→UTF-8→edit→UTF-8→UTF-16LE round trip, re-verified byte-identical encoding/no BOM after write.
- [x] 2.3 Insert `## Ejecutar con Docker (Fase 4)` into `README.md` after `## Ejecutar` — content per design.md: run/stop commands, baked-model note, `### Variables` table, `### Usar el memory/ real en producción` (`:ro` + `MEMORY_DIR`), `### Seguridad` (unauthenticated port note).

## Phase 3: Build + Runtime Smoke Verification

No new Python code → no unit-test surface. Verification IS the build + run per design's Testing Strategy table.

Docker Desktop was started mid-change; the orchestrator ran the smoke test directly.

- [x] 3.1 `docker compose build` — succeeded (293.6s pip install layer + 10.3s model-bake layer), no errors.
- [x] 3.2 `docker compose up -d` with **no `.env` present** — container created/started without error, confirming `required: false` doesn't fail on a clean checkout.
- [x] 3.3 `docker ps` shows `bob-asistente-voz-app-1` reaching `healthy` (no `.env`, 13s to healthy) — confirms missing `GROQ_API_KEY` doesn't block startup. Also confirmed `GET /_stcore/health` and `GET /` both return HTTP 200 from the host.
- [ ] 3.4 Upload one file per format (wav/mp3/m4a/ogg) via UI — transcription succeeds (gate for future ffmpeg-drop decision, out of scope here). **Deferred** — requires manual browser interaction with real audio files; not exercised by this automated pass.
- [ ] 3.5 Disconnect container network, retry a transcription — succeeds, proving the bake removed the runtime download dependency. **Deferred** — same reason as 3.4 (needs a real transcription request to test against).
- [ ] 3.6 With no `.env`, click "Generar descripción" — existing lazy-failure error appears only on click, not at startup. **Deferred** — needs manual UI interaction; startup-side of this (no crash/blocking with no `.env`) is already confirmed by 3.2/3.3.
- [ ] 3.7 Set `BOB_HOST_PORT=8599` with 8501 occupied — UI reachable at `:8599`. **Deferred** — port-conflict scenario not exercised this pass; `${BOB_HOST_PORT:-8501}` substitution itself is standard Compose behavior, not a novel risk.
- [x] 3.8 `docker images bob-asistente-voz:latest` — **2.21GB**. Recorded in verify report; exceeds the ~800MB-1.3GB estimate but user explicitly said image size is not a concern for this internal tool (no action needed).
- [x] 3.9 `docker compose down` — container stopped/removed, network removed cleanly, no orphaned resources left behind.
- [x] 3.10 Ran host `python -m pytest -q` — 118/118 passed, confirming zero app-source regression (Fase 4 touched no Python files).

## Phase 4: Cleanup

- [ ] 4.1 Confirm `git status` shows only `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `README.md` as tracked changes (plus the manual `.env.example` edit) before opening the PR. **Partially checked**: `git status --porcelain` confirms only `README.md` (modified), `.dockerignore`, `Dockerfile`, `docker-compose.yml` (untracked/new) plus the `openspec/changes/asistente-voz-fase4/` planning artifacts — no unintended files touched. Left unchecked pending the manual `.env.example` edit and final pre-PR review.
