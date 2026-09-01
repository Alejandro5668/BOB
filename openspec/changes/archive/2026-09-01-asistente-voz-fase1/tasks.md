# Tasks: Voice Assistant for Analysts — Fase 1

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 550-700 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 bootstrap → PR2 transcribir.py → PR3 generar_descripcion.py → PR4 app.py |
| Delivery strategy | single-pr |
| Chain strategy | size-exception |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: size-exception
400-line budget risk: High

Note: estimate exceeds the 400-line budget; `single-pr` forces a `size:exception` decision before apply. Reconsider `feature-branch-chain` if the maintainer prefers smaller reviews.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Repo bootstrap files | PR1 | N/A — config only | N/A — no runtime behavior | delete 4 root files |
| 2 | `transcribir.py` + tests | PR2 | `pytest tests/test_transcribir.py` | N/A — real `base` model E2E deferred (integration, opt-in `-m slow`) | delete `transcribir.py`, `tests/test_transcribir.py` |
| 3 | `generar_descripcion.py` + tests | PR3 | `pytest tests/test_generar_descripcion.py` | N/A — `GROQ_API_KEY` unprovisioned, mocked client only | delete `generar_descripcion.py`, its test |
| 4 | `app.py` Streamlit shell | PR4 | `streamlit run app.py` (manual smoke) | Manual: record/upload → transcript → description | delete `app.py` |

## Phase 1: Repo Bootstrap
- [x] 1.1 `requirements.txt`: streamlit>=1.40, faster-whisper>=1.0.3, av>=12, groq>=0.11, python-dotenv, pytest.
- [x] 1.2 `.gitignore`: `.env`, `__pycache__/`, `.venv/`, `*.wav`.
- [x] 1.3 `.env.example`: `GROQ_API_KEY=your-key-here` placeholder, never a real value. Created manually by the maintainer — the agent's permission system hard-denies any Write/Bash/Read operation on `.env*` paths (a deliberate secret-leakage guardrail), so this one file could not be created by any SDD phase agent.
- [x] 1.4 Update `CLAUDE.md`: fill run command, port, pre-push check placeholders for Python/Streamlit.

## Phase 2: `transcribir.py` (audio-transcription spec)
- [x] 2.1 Define `ErrorDependenciaAudio`, `ErrorTranscripcion`; `verificar_dependencias()` via `importlib.util.find_spec("av")`, raises with install instructions.
- [x] 2.2 Lazy `WhisperModel("base", device="cpu", compute_type="int8")` singleton loader.
- [x] 2.3 `transcribir_archivo(ruta, *, on_progress=None, idioma="es", vad=True)`: iterate `transcribe(..., vad_filter=vad, language=idioma, beam_size=1)` segment generator, call `on_progress(segment.end / info.duration)` per segment.
- [x] 2.4 `transcribir_bytes(datos, sufijo=".wav", *, on_progress=None)`: write to `NamedTemporaryFile(delete=False)`, close handle **before** transcribing (Windows forbids reopening an open temp file), `finally: os.unlink(path)` — must clean up on both success and exception.
- [x] 2.5 Wrap decode/inference exceptions into `ErrorTranscripcion`, re-raised typed (temp file still unlinked).

## Phase 3: `generar_descripcion.py` (jira-description-generation spec)
- [x] 3.1 Define `ErrorConfiguracion`, `ErrorGeneracion`.
- [x] 3.2 `SYSTEM_PROMPT` (7 rules incl. anti-invention rules 3-6: use only transcript facts, no implementation-detail speculation) + `---`-delimited `PLANTILLA_USUARIO`.
- [x] 3.3 `_crear_cliente()`: `os.environ.get("GROQ_API_KEY", "").strip()` → raise `ErrorConfiguracion` before any HTTP call if absent/blank.
- [x] 3.4 `generar_descripcion(transcripcion, *, cliente=None, modelo=MODELO)`: inject/construct client, `chat.completions.create(system+user, temperature=0.2, max_tokens=1024)`; catch SDK auth/API errors into generic `ErrorGeneracion` — key value never interpolated into messages/logs/UI.

## Phase 4: `app.py` (Streamlit shell)
- [x] 4.1 `load_dotenv()`; guard `hasattr(st, "audio_input")`, always render file-upload fallback (1.40 floor).
- [x] 4.2 Wire `st.audio_input`/upload → `transcribir_bytes(...)` with `st.status`/`st.progress` callback bound to `on_progress`.
- [x] 4.3 Editable `st.text_area` for transcript, backed by `session_state.transcripcion`.
- [x] 4.4 "Generar descripción" button: guard empty transcript (disable/warn, no API call), call `generar_descripcion`, render editable `st.text_area` for the result.
- [x] 4.5 Map `ErrorDependenciaAudio`, `ErrorTranscripcion`, `ErrorConfiguracion`, `ErrorGeneracion` to `st.error` — no raw tracebacks, no key leakage.

## Phase 5: Tests
- [x] 5.1 `tests/test_transcribir.py`: fake model injected via the loader seam returns a canned `(segments, info)`; assert temp file deleted on success **and** on raised exception (`tmp_path` + `monkeypatch`).
- [x] 5.2 Same file: assert `on_progress` receives monotonic values in `[0, 1]`; assert missing `av` raises `ErrorDependenciaAudio` (`monkeypatch` on `find_spec`).
- [x] 5.3 `tests/test_generar_descripcion.py`: `monkeypatch.delenv("GROQ_API_KEY")` → assert `ErrorConfiguracion`, no network call made.
- [x] 5.4 Same file: `FakeGroq` object recording `chat.completions.create` kwargs — assert prompt text contains rules 4-5 and the transcript verbatim, `MODELO` sent, returned content correctly unwrapped, no real network call.

## Phase 6: Cleanup / Verification
- [x] 6.1 Run full `pytest` suite; confirm zero real network calls anywhere. (`pytest tests/` → 7 passed, all Whisper/Groq calls are fakes/mocks.)
- [x] 6.2 Confirm `.env` and `*.wav` are git-ignored; confirm no secret committed. (`.gitignore` has both patterns; nothing committed yet — repo's only tracked file remains `README.md`.)
- [x] 6.3 Cross-check every scenario in both `specs/*/spec.md` files maps to a task/test above; note `GROQ_API_KEY` provisioning and manual E2E remain blocked per design's Open Questions. Audio-capture UI scenarios and Spanish-prose-output scenario are inherently manual/Streamlit-runtime or require a real LLM call — consistent with design's Testing Strategy table (no automated test claimed for those). `.env.example` (1.3) is the one exception below.
