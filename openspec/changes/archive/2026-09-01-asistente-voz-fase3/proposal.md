# Proposal: Structured Markdown Ticket Output — Fase 3

## Intent

Fase 1/2 produce free Spanish prose, so the analyst must still reshape every generated text into ticket form before pasting it into Jira, and developers receive an unstructured paragraph with no predictable place for the affected module or the reproduction path. Fase 3 makes the model emit a fixed, locked Markdown template — with sections omitted rather than invented when the analyst never said them.

## Scope

### In Scope
- Rewrite `SYSTEM_PROMPT`, `SYSTEM_PROMPT_CON_CONTEXTO`, `REGLAS_CONTEXTO`, `PLANTILLA_USUARIO*` to require the locked template (`## Módulo afectado`, `## Qué pasó`, optional `## Pasos para reproducir`, optional `## Resultado esperado vs. obtenido`), inverting rules 1 and 7.
- Per-section omission rules: omit heading **and** body when the analyst did not state steps / did not state an expectation. Never fill with "no especificado".
- Fixed fallback `Módulo afectado: no identificado` when Fase 2 retrieval matched nothing (section is never omitted).
- Forbid code fences / preamble around the response.
- Lightweight pure-function post-processor (defense-in-depth): when a `## Resultado esperado vs. obtenido` section's body is only generic filler, REPLACE it with a fixed notice (`Resultado esperado vs. obtenido: no se pudo determinar de forma confiable`) rather than silently deleting the section — same "system tried and failed, say so" principle as the `Módulo afectado: no identificado` fallback. Also defensively strips a wrapping code fence.
- Tests: prompt-shape assertions plus post-processor unit tests (no API key required).
- **Prompt repository**: extract all system/user prompt constants out of `generar_descripcion.py` into a new dedicated `prompts.py` module at repo root. Each prompt gets a distinctive, role-descriptive name (e.g. `GENERADOR_DESCRIPCION_TICKET`, `GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO`) and a short docstring stating its role/use case — prompts stay short and consistent, not padded. `generar_descripcion.py` imports from `prompts.py` instead of defining prompt text inline. This is the first entry in what should become the project's prompt repository as more AI-calling features are added later — one module today, split into a `prompts/` package only if/when a second unrelated AI feature needs its own prompts (not speculatively now).

### Out of Scope
- Fase 4 (Docker/nginx deploy), Fase 5 (history, reindex, model tuning).
- Any change to `contexto_memoria.py` or `transcribir.py`.
- `app.py` rendering changes — it keeps displaying raw text in the editable `text_area`.
- Second-LLM verification of semantic grounding (exploration Approach 3, rejected as disproportionate).

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `jira-description-generation`: **MODIFIED** — `Spanish Prose Output` is inverted and renamed to `Structured Markdown Ticket Output` (output MUST follow the locked template, not free prose). The spec phase MUST write this as a MODIFIED delta referencing the superseded requirement, plus a new explicit MUST NOT requirement for the omit-if-not-stated rule, and a requirement for the `no identificado` module fallback.

## Approach

Exploration Approach 2. The system prompt carries the literal template skeleton as a format anchor, so the model has an exact shape to copy rather than a description to interpret. Prompt instructions remain the **primary** control; the post-processor is best-effort defense-in-depth over the single known failure shape (a hallucinated generic expectation), never a guarantee — the spec MUST NOT claim it eliminates the risk.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `prompts.py` | New | Prompt repository: named, documented system/user prompt constants |
| `generar_descripcion.py` | Modified | Imports prompts from `prompts.py`; new post-processor helper |
| `tests/test_generar_descripcion.py` | Modified | Template/omission-rule prompt assertions; post-processor unit tests |
| `openspec/specs/jira-description-generation/spec.md` | Modified | Delta written in spec phase |
| `app.py` | Unchanged | No-code-fence rule becomes load-bearing for display |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Model invents a generic "Resultado esperado" despite the rule | Med | Explicit MUST NOT in prompt + post-processor blocklist; flagged as residual |
| Blocklist false positive replaces a real expectation with the fallback notice | Low | Match only when the section body is *entirely* filler; unit-tested both ways |
| No `GROQ_API_KEY` — real model compliance unverifiable in CI | High | Prompt-shape + pure-function tests only; manual smoke test as explicit follow-up |
| Model wraps output in a code fence | Med | Explicit prompt prohibition + defensive fence stripping |
| No fixture documents a sub-module, so sub-module naming is untested | Med | Add a synthetic fixture or inline context string in the design/apply phase |

## Rollback Plan

Prompt-constant edits plus one additive pure function in a single file. Revert the single PR to restore Fase 2 prose output byte-for-byte. No data, no schema, no migration, no deploy state. Partial rollback is also possible without a revert: disabling the post-processor call leaves prompt-only behavior (exploration Approach 1) intact.

## Dependencies

- Fase 2 retrieval (`contexto_memoria.py`) already merged and unchanged — supplies the module name for `## Módulo afectado`.
- `GROQ_API_KEY` still unprovisioned; blocks end-to-end behavioral verification, not merge.

## Success Criteria

- [ ] Every generated description starts with `## Módulo afectado` and contains `## Qué pasó`.
- [ ] A transcript with no stated expectation yields output with **no** `## Resultado esperado vs. obtenido` heading at all.
- [ ] A transcript with no stated steps yields output with no `## Pasos para reproducir` heading, and no "no especificado" filler anywhere.
- [ ] No module match yields the literal `Módulo afectado: no identificado`.
- [ ] Post-processor unit tests pass without a network call: filler expectation replaced with the fixed "no se pudo determinar de forma confiable" notice, genuine expectation kept verbatim, absent section stays absent (no-op).
- [ ] Output contains no wrapping code fence or preamble.

## Proposal question round

Resolved and locked with the user before this proposal: approach, exact template, no raw-transcript section, `no identificado` fallback, and (just resolved) the post-processor surfaces a fixed notice instead of silently stripping — same principle applied consistently to both "system tried and failed to identify something" cases (module, expectation). One implementation-level gap remains, deferrable to `sdd-design` as a non-product decision (a concrete phrase list, not a behavior choice):

1. The exact generic-filler blocklist phrases (which Spanish phrasings count as "invented expectation"?).
