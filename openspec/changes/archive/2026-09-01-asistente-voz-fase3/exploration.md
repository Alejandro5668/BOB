# Exploration: Fase 3 — Structured Markdown template for Jira description output

## Current State

`generar_descripcion.py` currently produces free Spanish prose, explicitly forbidding structure:
- `SYSTEM_PROMPT` rule 1: "Escribe en prosa libre... Sin secciones, títulos, viñetas ni plantillas."
- `SYSTEM_PROMPT` rule 7: "Responde solo con la descripción, sin preámbulos ni markdown."
- `SYSTEM_PROMPT_CON_CONTEXTO` = `SYSTEM_PROMPT + REGLAS_CONTEXTO` (rules 8-12), used only when `contexto_memoria.buscar_contexto()` returns non-empty text.
- `generar_descripcion()` returns `respuesta.choices[0].message.content` raw, no post-processing.
- `app.py` (lines 87-105) just displays that string verbatim in an editable `st.text_area` — no parsing, no markdown rendering, no validation.
- `openspec/specs/jira-description-generation/spec.md`'s "Spanish Prose Output" requirement states output "MUST be free-form Spanish prose without sectioned ticket structure" — the exact requirement Fase 3 must invert (MODIFIED, not ADDED, delta).
- `memory/modulos/*/_modulo.md` fixtures (gestion_riesgos, planes_accion, auditorias_internas) are flat — none document an internal sub-module subdivision, so the template's sub-module-naming behavior has no real fixture to validate against.
- `tests/test_generar_descripcion.py` uses a `FakeGroq` returning a fixed canned string regardless of input — existing tests verify only constructed prompt strings, never actual model behavior. `GROQ_API_KEY` is unprovisioned.

## Affected Areas
- `generar_descripcion.py` — `SYSTEM_PROMPT`, `SYSTEM_PROMPT_CON_CONTEXTO`, `REGLAS_CONTEXTO`, `PLANTILLA_USUARIO*`, rules 1/7 rewritten; likely new template constant + optional post-processing helper.
- `tests/test_generar_descripcion.py` — new prompt-shape assertions plus, if added, pure-function tests for the post-processor.
- `app.py` — no functional change expected, but "no code fences" instruction becomes load-bearing (raw text shown verbatim).
- `openspec/specs/jira-description-generation/spec.md` — "Spanish Prose Output" becomes MODIFIED; new explicit MUST NOT requirement for the omit-if-not-mentioned rule with scenarios.
- `contexto_memoria.py` — confirmed untouched.

## Approaches

1. **Prompt-only restructuring** — flip rules 1/7, embed template + omission rules in system prompt only.
   - Pros: simplest, matches Fase 1/2 pattern, no new failure surface.
   - Cons: the change's single strictest rule has zero automated defense against non-compliance.
   - Effort: Low.
2. **Prompt restructuring + lightweight regex/keyword post-processor** for the known "generic hallucinated expectation" failure shape (blocklist phrases inside a detected "Resultado esperado" section → strip section if matched).
   - Pros: directly targets the user's named risk; fully unit-testable today with zero API key (pure string in/out); verifiable in CI where Approach 1 cannot be.
   - Cons: blocklist is incomplete (false negatives for novel paraphrases; some false-positive risk); rule now lives in two places (prompt + code) that must stay in sync.
   - Effort: Medium.
3. **Full semantic grounding check via a second LLM call** — verify the produced expectation is grounded in the transcript.
   - Pros: only approach addressing grounding generally.
   - Cons: doubles latency/cost/test-mocking surface, contradicts the "token-conscious" bar, adds deployment risk before even one real Groq call is provisioned.
   - Effort: High.

## Recommendation

Approach 2, framed explicitly as best-effort defense-in-depth (not a guarantee the spec claims eliminates hallucination risk) — Approach 1 leaves the change's most-insisted-upon rule with no test coverage at all; Approach 3 is disproportionate for a token-conscious internal tool without even a provisioned API key.

## Risks

- Omission-rule compliance is a known LLM weakness; even Approach 2 only catches anticipated generic-filler phrasing, not arbitrary hallucinated content.
- No `GROQ_API_KEY` provisioned: real model behavior is untestable in this environment — only prompt-shape and post-processor unit tests are feasible pre-merge; genuine confidence requires a manual smoke test later, a residual risk `sdd-verify` cannot close.
- Spec-level reversal of "Spanish Prose Output" must be written as MODIFIED, not ADDED.
- "Módulo afectado" has no stated omission fallback (unlike the two optional sections) — undefined behavior when no module context matched and the transcript never names one; needs a product decision at `sdd-propose`/`sdd-design`, not assumed here.
- No existing fixture exercises sub-module naming — any test for it needs synthetic content.
- Code-fence leakage risk: raw text shown verbatim in `app.py`'s text_area; rule 7's replacement must explicitly forbid fences, and the post-processor should defensively strip a stray fence too.

## Ready for Proposal

Yes, with three explicit decisions flagged for `sdd-propose`: (a) "Módulo afectado" fallback wording, (b) exact blocklist heuristic for the post-processor, (c) MODIFIED-delta framing for "Spanish Prose Output".
