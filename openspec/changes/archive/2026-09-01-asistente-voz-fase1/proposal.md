# Proposal: Voice Assistant for Analysts — Fase 1

## Intent

Analysts describe client-reported issues verbally, then hand-write Jira descriptions — slow, inconsistent, and detail-losing. Fase 1 proves the smallest end-to-end slice: speak the issue, get a Jira-ready description to paste. Success = a non-coding analyst runs it locally and beats typing it by hand.

## Scope

### In Scope
- Streamlit UI at repo root: record or upload audio, one screen.
- Local CPU transcription via `faster-whisper` model `base` into an **editable** transcript box.
- Audio can run **several minutes** (not a short clip) — transcription must show progress and not block/freeze the UI while it runs.
- "Generar descripción" sends **only** the transcript to Groq (`llama-3.3-70b-versatile`) with a fixed prompt template, output in **Spanish prose** (no sectioned format yet — that's Fase 3).
- Result in an editable box the analyst copies into Jira manually.
- Repo bootstrap: `requirements.txt`, `.gitignore`, `.env.example`, stack-level `CLAUDE.md`.
- Temp audio deleted after transcription.

### Out of Scope
- RAG / `memory/` indexing (Fase 2) — no retrieval in the Groq call.
- Prompt tuning to real ticket style (Fase 3).
- Docker / nginx (Fase 4). History, reindex, model tuning (Fase 5).
- Jira API integration — copy/paste only.

## Capabilities

### New Capabilities
- `audio-transcription`: capture/upload audio, transcribe locally to an editable transcript, clean up temp files.
- `jira-description-generation`: send an approved transcript to Groq, return an editable Jira-ready description.

### Modified Capabilities
- None (greenfield; `openspec/specs/` is empty).

## Approach

Lightweight layered structure (exploration Approach 2) at **repo root**: thin `app.py` Streamlit shell, `transcribir.py`, `generar_descripcion.py`. The UI never calls Whisper or Groq directly. This is the exact seam Fase 2 needs (retrieval between transcribe and generate) and Fase 3 needs (prompt isolated in `generar_descripcion.py`) — no rewrite later. `GROQ_API_KEY` read from environment only.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `app.py` | New | Streamlit shell, session state, two editable boxes |
| `transcribir.py` | New | faster-whisper `base`, temp-file cleanup |
| `generar_descripcion.py` | New | Groq client + prompt template |
| `requirements.txt` | New | Pinned streamlit, faster-whisper, groq, av |
| `.gitignore`, `.env.example` | New | Secrets convention (first in repo) |
| `CLAUDE.md` | Modified | Fill Python/Streamlit placeholders |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `base` mis-transcribes jargon (`gsr_riesgos`) | High | Transcript editable before generation — accepted tradeoff |
| Multi-minute audio takes long on CPU / blocks the UI | High | Run transcription with a visible progress spinner/status; consider VAD filter (faster-whisper's built-in `vad_filter`) to skip silence and cut wall time |
| Missing ffmpeg/`av` breaks decode | Med | Pin `av`; explicit setup error, not a stack trace |
| Groq key absent/invalid at runtime | Med | Fail fast with clear message; never hardcode |
| `st.audio_input` unavailable on old Streamlit | Med | Pin minimum Streamlit; upload path as fallback |
| No test tooling in repo | Med | Minimal pytest for both modules, mocked Groq client |

## Resolved Product Decisions

- **Recording length**: several minutes is expected (not a short clip) — design must not assume single-shot fast transcription.
- **Output format**: free Spanish prose for now; sectioned ticket format (context / repro steps / expected vs. actual) is explicitly Fase 3.
- **Language**: Spanish in, Spanish out.
- **Data sensitivity**: sending the transcript to Groq (external API) is accepted; no additional redaction/filtering required for this phase.
- **Output tone**: plain language only — the generated description MUST describe the observed error precisely, in terms a non-technical analyst understands, and MUST NOT invent/reference implementation details (classes, functions, internal causes) not present in the input. This constraint holds now and gets stronger once Fase 2 adds real module/table context — the model must ground itself in that context, not speculate technically.

## Note for Fase 2 (not part of this change)

The PDF's Fase 2 plan uses `sentence-transformers` + `Chroma` (vector embeddings) to search `memory/`. Given `memory/` is already structured by module name (`modulos/<name>/_modulo.md`), a simpler first pass may suffice: match the module name(s) mentioned in the transcript against real folder names and feed those files directly into the Groq prompt (large context window) — no vector index, no embeddings, no reindex pipeline. Only add embeddings if plain name-matching proves insufficient in practice. Flagged here for the Fase 2 exploration to evaluate, not decided now.

## Rollback Plan

All changes are additive greenfield files at repo root; no existing behavior is touched. Revert = `git revert` of the single PR (or delete the added root files). No data migration, no schema, no deployed service. Only residue: the `CLAUDE.md` placeholder edits, which revert in the same commit.

## Dependencies

- **BLOCKER — Groq API key not provisioned.** Free at console.groq.com. Code can be written and unit-tested with a mocked client, but end-to-end verification cannot pass until `GROQ_API_KEY` exists in the environment. Never committed.
- Python 3.10+ and ffmpeg locally.
- First run downloads Whisper `base` weights (network needed once).

## Success Criteria

- [ ] Analyst records/uploads audio (including multi-minute recordings) and sees an editable Spanish transcript, with visible progress while transcribing.
- [ ] "Generar descripción" returns a coherent Spanish-prose description from the (possibly edited) transcript.
- [ ] Generated text is editable and copy-pasteable into Jira.
- [ ] `GROQ_API_KEY` read from environment; no secret in git history.
- [ ] Temp audio removed after transcription.
- [ ] Both modules callable/testable without Streamlit running.
