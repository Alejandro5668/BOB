# Spec Impact: None

Fase 4 (standalone Docker packaging) is infrastructure/deployment, not
product behavior. It introduces no new capability and modifies none of
the existing ones (`audio-transcription`, `context-retrieval`,
`jira-description-generation`) — it must *preserve* them unchanged inside
a container, not alter their contracts.

Two existing requirements are load-bearing for this change and are
already specified elsewhere — Fase 4 does not restate them, only relies
on them holding true inside the container:

- `jira-description-generation` — "API Key Fail-Fast": `GROQ_API_KEY`
  absence must not block startup, only the "Generar descripción" action.
- `context-retrieval` — "Configurable, Read-Only Memory Location": a
  missing/unset `MEMORY_DIR` degrades non-blockingly.

No `openspec/specs/` domain is added or modified by this change. See
`design.md` and `tasks.md` for the actual deployment content.
