# BOB — Team Collaboration Guide

This file applies regardless of which subfolder you're working in. It
covers how collaborators (human and AI sessions) work together without
stepping on each other's work. Stack-specific rules belong in a nested
`<subdir>/CLAUDE.md` instead of here.

> How any task gets routed → `docs/architecture.md` §4 (the decision
> ladder). Consult it before starting any requested task: it decides
> whether the work goes direct, delegated, or through SDD, and whether it
> genuinely needs an issue/board card — don't infer that from the board
> rule below alone, it's coarser and misses that nuance (a 1-3 file change
> with one reasonable approach and low risk goes direct, no issue, no
> card). Worktree activation (below) is independent of that ladder — it
> applies whenever a second concurrent session exists, regardless of task
> size.

---

## Project setup (mandatory — read before improvising)

When asked to set up, start, "levantar", refresh, or verify the running
app is up to date — run:

```bash
./scripts/setup.sh
```

Idempotent, safe to re-run any time, including right after a merge. It
always rebuilds the Docker image and recreates the container from
scratch, so it can never silently keep serving a stale build.

**Why this is mandatory, not a suggestion:** this bit the project once —
a container sat running pre-migration code for 4 hours after a merge
because nobody rebuilt it, and a manual `streamlit run app.py` bypassed
Docker entirely and picked up the wrong `MEMORY_DIR` (the dev fixture
instead of the real docs folder mounted via
`docker-compose.override.yml`). Don't improvise a bare `streamlit run`
or a manual `docker compose up`/`build` sequence — use the script, so
every session (human or AI) gets the same guaranteed-fresh result.

If `.env` doesn't exist yet, the script creates it from `.env.example`
and prints which keys need to be filled in by hand (`ANTHROPIC_API_KEY`,
`ELEVENLABS_API_KEY`) — editing `.env*` itself remains a manual,
operator-owned step, never an AI-session action.

---

## Decision persistence rule (mandatory)

Any AI session's memory/continuity tooling is typically **local to each
machine** — it does not sync between collaborators. If one person makes an
architecture decision and it only lives in that local memory, nobody else
sees it and will build against a stale assumption.

**Rule:** any of the following must be written to a git-tracked file in the
same response/session that decides it — never left only in local
session memory:

- Architecture or design decisions
- API contract decisions (endpoint shape, request/response payload,
  roles/permissions)
- Workflow or convention changes
- Anything another collaborator needs to know to avoid duplicate or
  conflicting work

**Where to write it:**

| Decision scope | File |
|---|---|
| Tied to one feature/module being built via SDD | The change's spec/design artifacts (e.g. `openspec/changes/<change>/proposal.md`, `spec.md`, `design.md`) |
| Lasting convention, not tied to one feature | The relevant `CLAUDE.md` — this file, or a nested stack-specific one |

### One SDD change spanning multiple parallel PRs

When one SDD change fans out into several PRs in flight at once, only
**one** copy of the spec artifacts is canonical, and it must reach the
default branch through the **first** of those PRs to merge — never
duplicated or re-authored independently in each branch. Two branches that
each carry their own divergent copy of the same change's spec files will
conflict on merge even when the source code doesn't.

- Before starting the second (or third) PR of a fanned-out change, check
  whether the first PR already merged its spec artifacts. If yes, branch
  from that — don't re-copy or re-draft the spec.
- If the first PR hasn't merged yet, reference the still-open PR's spec
  instead of duplicating it.
- Whoever merges second rebases onto whatever landed first and drops their
  own duplicate spec files in favor of the one now on the default branch.

---

## Parallel work coordination

- <PLACEHOLDER: describe your project's module boundaries once they exist,
  e.g. "backend and frontend are independent projects on purpose (own
  lockfiles, own dependency manager) so each person can work without
  touching the other's files.">
- When a feature needs multiple layers/services, the API contract (schema,
  routes, roles) must be settled in an SDD spec/design **before** everyone
  starts implementing in parallel — not discovered mid-implementation.
- <PLACEHOLDER: if you regenerate a client/type layer from a schema, note
  the command and when it must be re-run, e.g. "after any backend
  schema/route change, regenerate the frontend TS client
  (`npm run generate:types`) in the same PR.">
- **No GitHub Projects board in use for this repo.** Skip the board-check
  and board-ownership rules below entirely until one is adopted.
- `.claude/hooks/board-context.mjs` and `.claude/hooks/skill-reminder.mjs`
  are wired but board-context has nothing to fetch without a board —
  see `TOOLS.md` / `docs/architecture.md`.
- `.claude/hooks/skill-reminder.mjs` reminds which project-specific
  skills/conventions apply the first time in a session that a file in a
  configured category is edited. Configure its `CATEGORIES` block per
  stack — ships empty.

---

## Prompt repository convention

Every prompt sent to an LLM (Groq, or any future provider) lives as a named
constant in `prompts.py` at repo root — never inline inside the module that
calls the API. Each prompt:

- Gets a distinctive, role-descriptive name (e.g. `GENERADOR_DESCRIPCION_TICKET`)
  stating what it's for and, implicitly, which part of the project uses it.
- Has a short docstring/comment stating its role and use case — not a long
  design essay, just enough for the next person (or AI) to know when to use it.
- Stays short and consistent — no padding, no speculative instructions for
  scenarios that don't exist yet.

`prompts.py` starts as a single file. Only split it into a `prompts/` package
once a second, genuinely unrelated AI-calling feature needs its own prompts —
don't pre-build that structure for one feature's prompts.

---

## Transcription provider decision

`transcribir.py` calls the ElevenLabs Speech-to-Text API
(`ELEVENLABS_API_KEY`), not local `faster-whisper` — a deliberate
architecture change from Fase 1, made at the user's explicit request
after local `base`-model accuracy proved insufficient in real use.

**Why:** the user confirmed audio no longer needs to stay on-machine, so
transcription accuracy and low per-minute cost won over the
zero-network-dependency guarantee Fase 1 originally optimized for.
Groq's own hosted Whisper (`whisper-large-v3-turbo`) was considered and
rejected in favor of ElevenLabs specifically because the user asked for
an ElevenLabs-based model by name.

**How it's applied:** `contexto_memoria.nombres_conocidos()` supplies
known module names/aliases as ElevenLabs `keyterms` (vocabulary bias) —
the same problem `hotwords` would have solved for local Whisper, solved
instead at the new provider. When creating an ElevenLabs API key, grant
it **Speech to Text access only** — no other endpoint is used.

---

## Context retrieval decision

`contexto_memoria.py` no longer requires any fixed layout under
`MEMORY_DIR` (no `MEMORY.md` index, no `modulos/<nombre>/_modulo.md`
convention) — it discovers ANY `.md` file, anywhere in the tree, and asks
Groq itself which ones (if any) are relevant to a transcript, instead of
scoring them with our own lexical-matching heuristic.

**Why:** the real Kawak PHP documentation folder does not match the
schema Fase 2 originally assumed at all — no index file, no per-module
summary, modules as flat top-level folders each holding 10-30 per-screen
`.md` files. The user explicitly rejected requiring any fixed structure:
"no quiero una limitante... no serviría de nada la aplicación." Leaning
on Groq's own judgment for relevance, rather than a hardcoded scoring
algorithm, was an explicit request too.

**How it's applied:** `listar_documentos()` recursively finds every
`.md` file under `MEMORY_DIR` (capped at `MAX_DOCUMENTOS_LISTADOS` as a
volume safety valve, not a schema requirement) and builds a lightweight
`ruta: vista previa` listing. `elegir_documentos_relevantes()` sends that
listing to Groq (`MODELO_SELECTOR`, currently `openai/gpt-oss-20b`) and
only trusts paths the model picked that were actually in the listing
(never an invented path). `nombres_conocidos()` (used for ElevenLabs
`keyterms`) now derives from folder/file basenames found on disk instead
of a parsed alias list — also schema-free.

**Real corpus constraint (verified live, not assumed):** the real Kawak
docs folder is 273 files; a single-request listing exceeded Groq's
free-tier TPM limit for `gpt-oss-20b` (8000 TPM; a single listing needed
~14000). `elegir_documentos_relevantes()` batches the listing
(`CARACTERES_POR_LOTE`) and stops early once `MAX_ARCHIVOS_SELECCIONADOS`
is reached — this must keep scaling as `memory/` grows, not just work
for today's fixture.

**`gpt-oss` reasoning-token gotcha (verified live):** `openai/gpt-oss-20b`
reasons internally before answering, and those reasoning tokens count
against `max_tokens`. A 200-token cap on the selector call cut reasoning
off mid-thought, leaving an empty completion that Groq's
`response_format: json_object` mode then rejected with a 400. Fix:
`reasoning_effort="low"` (cuts reasoning-token cost roughly 10x, measured
227→14 on a real batch) plus a generous `max_tokens` (500 for the
selector, 150 for the verifier below). Any future call to a `gpt-oss`
model with JSON mode must account for this — don't reintroduce a small
`max_tokens` without `reasoning_effort` set.

## Anti-hallucination check decision

`generar_descripcion.py`'s "Resultado esperado vs. obtenido" defense-in-depth
no longer matches the model's output against a fixed blocklist of ~57
generic phrases — it asks Claude Haiku 4.5 itself (`MODELO_AUXILIAR`, same
model as generation) whether the stated expectation is explicitly
grounded in the transcript, replacing the section with a fixed notice
only when the model says it isn't.

**Why:** the user explicitly distrusted the fixed-phrase-array approach
("no me convencen del todo, prefiero algo más útil, más funcional") — a
static list can never cover every way of phrasing an invented
expectation.

**Failure policy:** if the verifier call itself fails (network error,
malformed JSON), default to `True` (assume grounded, keep the model's
original text) — a broken verifier must never silently erase real
analyst-provided content.

### Guardrails catalog (RAG anti-hallucination rules)

Every rule below exists to keep a response tied to what the analyst
actually said or what the retrieved documentation actually contains —
never to what the model thinks is plausible. Two enforcement tiers exist,
and the table says which one covers each rule:

- **Prompt-only**: an instruction in the system prompt (`prompts.py`). Cheap,
  but nothing double-checks the model actually followed it.
- **Prompt + verifier**: the prompt rule PLUS a second, cheap Haiku call
  (`_pedir_json`-based, same pattern for all of them) that audits the
  specific claim after generation and degrades to a safe fixed fallback if
  it isn't grounded. This is strictly stronger — it's what catches the
  model breaking its own prompt rule.

| Guardrail | Rule(s) | Tier | Where |
|---|---|---|---|
| No inventing incident facts beyond the transcript | 8, 16, 17 | Prompt-only | `GENERADOR_DESCRIPCION_TICKET`/`REGLAS_CONTEXTO_MODULO` |
| No implementation detail (classes, tables, endpoints) | 9 | Prompt-only | `GENERADOR_DESCRIPCION_TICKET`, `RESPONDEDOR_CONSULTA_DOCUMENTACION` |
| No technical-cause diagnosis | 10 | Prompt-only | `GENERADOR_DESCRIPCION_TICKET` |
| No filler placeholders in omitted sections | 3, 4 | Prompt-only | `GENERADOR_DESCRIPCION_TICKET` |
| Module/screen/functionality names must be quoted literally, never paraphrased | 6, 14, 19 | **Prompt + verifier** | `_verificar_modulo_afectado` (`generar_descripcion.py`), only runs when context was retrieved |
| "Resultado esperado" must be grounded in the transcript | 5 | **Prompt + verifier** | `_verificar_resultado_esperado` (`generar_descripcion.py`) |
| Q&A: module/screen names must be quoted literally | (Q&A prompt) | Prompt-only | `RESPONDEDOR_CONSULTA_DOCUMENTACION` — no verifier yet (see below) |
| Q&A: no-information notice reserved for zero-context case | (Q&A prompt) | Prompt-only + code-level (`TIPO_SIN_INFORMACION`) | `consultar_documentacion.py` |
| Selected document paths never invented | (retrieval) | **Code-level** (stronger than a verifier: never trusts a path the model didn't actually list) | `elegir_documentos_relevantes` (`contexto_memoria.py`) |

**Why module naming got a verifier and Q&A didn't (yet):** a real failure
motivated this — the analyst said "listado único de documentos" (also
present in the retrieved documentation verbatim) and the model still wrote
"edición masiva de documentos" in `## Módulo afectado`, an invented name.
The ticket template has one fixed, always-present section for this
(`## Módulo afectado`), so a verifier can extract and check it precisely.
The Q&A mode's answer is free-form prose with no fixed extraction point —
adding an equally precise verifier there would need a different mechanism
(candidate-name extraction first), which is a real "no sobreingeniería"
tradeoff: documented here as a known gap, not silently ignored.

**Failure policy for every verifier above:** never raises, defaults to
keeping the model's original claim on any failure (network error,
malformed JSON) — a broken verifier must never erase real content, only
a confirmed "not grounded" verdict triggers the fallback.

---

## Logging convention

`logging_config.py` wires stdlib `logging` once at process start (called
from `app.py`, the only entrypoint): console output (captured by
`docker compose logs`) plus a rotating file at `logs/app.log`
(bind-mounted in `docker-compose.yml` so it survives container
recreation; gitignored).

Every module that can fail (Groq calls, transcription, memory retrieval)
logs the **real** exception (`type(exc).__name__`, message) at the point
of failure, before wrapping it in the short, friendly Spanish message the
UI shows. Never log the `GROQ_API_KEY` value or full audio bytes. When a
user hits a generic UI error, check `logs/app.log` (or `docker compose
logs`) for the actual cause before guessing.

---

## Concurrent agent sessions in the same local clone

Two collaborators' agent sessions can end up running against the exact
same clone (one machine, one folder) at the same time — this is not an
edge case, it happens whenever one person kicks off a second session while
the first is still working. `HEAD` and the working tree are one per
folder: if either session runs `git checkout`/`switch`, it moves the
other's checkout out from under it.

### Rule: one git worktree per active session

The moment a second session is going to make edits or run
git/branch-affecting commands in this repo while another session is also
active, each session works from **its own git worktree**.

```bash
git worktree add ../<repo>-<short-slug> <module>/prN-description
git worktree list
git worktree remove ../<repo>-<short-slug>
```

- Worktrees live as **siblings** of the main clone, never nested inside it.
- Branch naming stays `<module>/prN-description`; the worktree directory
  name is just a readable slug for that branch.
- The main clone stays on the default branch when idle — don't leave it
  parked on a feature branch between sessions.

`.claude/hooks/worktree-guard.mjs` automates detecting this and blocking
edits in the shared clone once a second session is live — see
`docs/architecture.md` §2 for exactly how.

### Checking for a concurrent session is the agent's job, not the human's

Don't ask "is another session running?" as the first move — check before
editing or running any git/branch-affecting command in the main clone (a
session already working from its own worktree doesn't need to re-check).
Signals to combine (none alone is proof):

- `git worktree list` — other worktrees besides the main clone.
- `git status` — uncommitted changes this session didn't make, especially
  with recent mtimes.
- Streamlit dev server on port 8501 (`streamlit run app.py`, the default
  Streamlit port).
- `.git/index.lock` existing — a git operation is in progress elsewhere.

If signals point to concurrent activity, set up a worktree before
continuing. Only ask the human when signals are genuinely ambiguous even
after checking.

### What a new worktree does NOT get for free

A worktree shares git history/objects with the main clone, but not
uncommitted or gitignored local state — env files, dependency installs.
`scripts/setup-worktree.sh` automates seeding these; customize its
placeholder sections for your stack.

**Dev-server port convention:** run with `streamlit run app.py`; the main
clone stays on the default port 8501. Each additional worktree runs its own
instance on the next free port (`streamlit run app.py --server.port 8502`,
`8503`, ...).

**Shared local services (e.g. a dev database):** <PLACEHOLDER: if your
stack has a service that only one worktree should run (a fixed host port,
a shared container), describe the convention here — which worktree runs
it, how the others point at it, and how to avoid two worktrees running
conflicting migrations against it concurrently.>

### When a worktree is overkill

A single session working alone in this clone doesn't need a worktree —
this only kicks in once a *second* session is going to be concurrently
active here. A session that's only answering questions or reading code (no
edits, no branch switches) doesn't need one either.

---

## Branching and delivery

- One branch per sub-issue/work unit: `<module>/prN-description`.
- Merge to the default branch as soon as a PR's own checks are green.
  Don't accumulate unmerged work on a long-lived branch.
- **Rebase-before-merge for stacked/parallel PR chains.** A PR's own CI run
  only proves it's green against the base it branched from — not against
  the default branch plus whatever else just merged ahead of it. Run
  `./scripts/check-branch-overlap.sh` before merging the 2nd+ PR of a batch
  that shares scope with one that just merged; rebase onto the current tip
  and wait for checks to go green on that rebased state.

## Before every push (mandatory)

Another collaborator's session may have pushed since your last pull.

Run `./scripts/check-branch-overlap.sh` before pushing, every time:
- No new commits on the remote default branch since your base → push
  normally.
- New commits but no file overlap → `git rebase origin/<default-branch> &&
  git push`.
- File overlap → STOP. Read both diffs in full before touching anything;
  resolve the conflict deliberately during the rebase. Never force-push
  over someone else's work.

## Local pre-push checks

Run `pytest` from the repo root before every push — it covers
`transcribir.py`, `generar_descripcion.py`, and `contexto_memoria.py`
(Fase 2's read-only `memory/` module-context retrieval, see `README.md`
for the `MEMORY_DIR` / `memory/` contract) with mocked/fake
Whisper/Groq/context providers, no network calls, no `GROQ_API_KEY`
required. No git hook wired yet; run it manually until one is added. No
GitHub Actions CI configured for this repo yet.

## Deploying after a merge

<PLACEHOLDER: no deploy pipeline yet — describe it here once one exists
(auto-deploy on push? manual script? which environments?).>

## Commits and Pull Requests

- Conventional commits (`feat`/`fix`/`docs`/`chore`/`refactor`/...), never
  an AI-attribution trailer.
- One commit per logical concern — don't bundle unrelated changes into one
  commit just because they landed in the same session.
- PR body template, in this order:
  - `## Problem`: what was broken or missing, and why it matters.
  - `## Solution`: what changed technically (the "how").
  - `## Impact`: which endpoints/screens/contracts this touches; breaking
    changes if any.
  - `## Verification`: tests run, manual steps, screenshots if frontend.
- Reference the sub-issue the PR closes (`Closes #N`), once a board is
  adopted, so its `Status` advances automatically on merge.

---

## How to pick up a task (no board yet)

Without a board, work is tracked by branch + PR directly. Which
implementation route a task takes depends on its review tier (see below) —
not every task needs the full SDD ramp.

**Tier 1, or any Tier 2/3 task with a genuinely open design question or a
cross-collaborator contract at stake:** full SDD cycle, mandatory.

```
1. Explore + propose (spec-driven-development tooling's explore/propose phase)
2. Once the proposal is approved: spec + design + tasks
3. Implementation on a branch named <module>/prN-description
4. Validation against the spec/design/tasks contract
5. Open PR
6. Archive the SDD change
```

**Tier 3, and Tier 2 work whose scope is already well understood** (no open
design question, nothing another collaborator needs to agree on first):
skip the spec/design ceremony. Apply the decision ladder
(`docs/architecture.md` §4 — direct inline for a mechanical 1-3 file
change, one delegated writer for anything bigger), implement on a branch,
and open the PR.

### Review tiers

| Tier | When | What it means |
|---|---|---|
| 1 | Auth, access control, tenant isolation, payments/money, or the contract of an endpoint already in production | Fresh-context review before merge — never the same session that wrote the change |
| 2 | Additive infra, no behavior change to existing endpoints | Full-diff self-review before opening the PR |
| 3 | Pure UI, docs, config | Tests + your own verification pass; no separate reviewer |

Trivial/docs-only changes need no formal review step at all — don't invent
ceremony where the risk doesn't justify it.

<PLACEHOLDER: fill in a table of this project's actual Tier-1 modules once
they exist, e.g. "payments", "auth", "multi-tenant data isolation" —
whatever your irreversible/high-blast-radius surfaces turn out to be.>
