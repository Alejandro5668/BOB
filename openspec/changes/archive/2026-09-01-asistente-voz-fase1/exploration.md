# Exploration: Voice Assistant for Analysts — Fase 1 (Transcription + basic generation, no RAG)

## Current State

BOB is confirmed near-empty: `README.md` (title only), `CLAUDE.md` (workflow conventions, no board), `docs/architecture.md` (AI-first engineering architecture for this repo's own tooling — unrelated to this product's RAG plan), `.claude/hooks/*`, `.codegraph/` (empty, no source indexed yet), `.atl/skill-registry.md`. No `openspec/` directory existed before this change, no application code, no Python tooling, no stack-specific nested `CLAUDE.md`, no tests. This is genuinely the first product change in this repo.

## Affected Areas

- Repo root layout — undecided: BOB root as the tool itself vs. a subfolder (e.g. `analista-asistente/` per the source planning PDF's own structure).
- `docs/architecture.md` / root `CLAUDE.md` — several `<PLACEHOLDER>` sections exist specifically for "once a stack exists."
- No stack-specific `CLAUDE.md` yet (needed once location is decided).
- Secrets handling — no `.gitignore`/`.env` convention exists; `GROQ_API_KEY` must never be committed.
- No Python lint/test/format convention established.

## Approaches

1. **Monolithic single-file Streamlit app** (`app.py` inline) — Pros: fastest working demo, matches Fase 1's minimal validation goal. Cons: mixes UI/transcription/generation, harder to extend for Fase 2 RAG insertion and Fase 3 prompt tuning. Effort: Low
2. **Lightweight layered structure** (`ui/app.py` + `transcription.py` + `generation.py`) — Pros: clean seam for Fase 2's retrieval step and Fase 3's prompt tuning without rewriting; each module independently testable. Cons: slightly more upfront structure. Effort: Medium
3. **CLI-first spike** (no Streamlit yet) — Pros: cheapest way to validate model/API quality. Cons: doesn't satisfy the plan's explicit Fase 1 objective (a Streamlit UI a non-coder analyst can use). Effort: Low

## Recommendation

Approach 2 (lightweight layered structure). Fases 2-3 are already confirmed to land directly on Fase 1's generation/transcription code per the user's own plan, so the small modularity cost now avoids near-certain rework in the next SDD change.

## Risks

- Groq API key provisioning not confirmed — blocks implementation start.
- Whisper model size (base vs. small) unresolved — affects latency and Spanish technical-vocabulary accuracy; mis-transcription would silently degrade downstream Jira output.
- Repo location for the tool (BOB root vs. subfolder) unresolved — affects every downstream artifact's file layout.
- Streamlit audio-recording widget maturity (native `st.audio_input` vs. third-party components) needs a version decision.
- `faster-whisper` audio decoding needs `av`/ffmpeg — could silently break on analysts' own machines pre-Docker.
- No Python tooling conventions (lint/test/format/secrets pattern) exist yet in this repo.
- Temporary audio files (client-reported issue content) need a cleanup story even without RAG.
- No tests exist yet in the repo — first-code-change verification risk.

## Ready for Proposal

Yes, conditional on `sdd-propose` explicitly resolving the three open questions (Groq key availability, Whisper model size, repo location) rather than assuming them.
