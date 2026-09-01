# AI-First Engineering Architecture

This is the reference for how AI agents (Claude Code + optional gentle-ai)
are used to build this product: what mechanisms exist, what each is for,
how a change actually flows from "idea" to "merged", and why it's built
this way. Read this before proposing a new tool, agent, or automation — the
answer to "do we need X?" is usually already here.

This is not a proposal. Everything described below is either implemented in
this repo, or explicitly marked as **not yet implemented**.

---

## 1. The three layers, end to end

Every AI-first workflow question in this project reduces to one of these
three concerns. Mixing them up is the mistake to avoid — each has its own
mechanism, and none replaces the others.

| Layer | Solves | Mechanism | Status |
|---|---|---|---|
| **1. Workspace isolation** | Two sessions (same person or different people) editing the same working tree at once | Git worktrees, one per active session + automatic detection via hook | Documented in root `CLAUDE.md`; hook in `.claude/hooks/worktree-guard.mjs` |
| **2. Shared task book** | "We keep re-explaining the same task to every new Claude session" | GitHub Issues as task-brief artifacts + a GitHub Projects board as shared state | See §4 |
| **3. Agent orchestration** | A task big enough to benefit from parallel/independent work | Claude Code sub-agents, the `Workflow` tool, custom agents under `.claude/agents/*.md` | Available; used selectively, not by default |

Personal continuity (persistent-memory tooling, e.g. Engram) is
deliberately **not** one of these layers — see §7.

---

## 2. Layer 1 — Workspace isolation (git worktrees)

### The mechanism

A git clone has exactly one `HEAD`, one working tree, one index. Two agent
sessions pointed at the same directory share all three — if either runs
`git checkout`, it moves the ground out from under the other. `git worktree
add <path> <branch>` creates a second working tree/HEAD/index that still
shares the same `.git` object database, so commits made in either are
visible to both, but neither can touch the other's branch or uncommitted
files.

### The rule

> The moment a second agent session is going to make edits or run
> git/branch-affecting commands in this repo while another session is also
> active, each session works from its own git worktree.

```bash
git worktree add ../<repo>-<short-slug> <module>/prN-description
git worktree list
git worktree remove ../<repo>-<short-slug>
```

Worktrees live as **siblings** of the main clone, never nested inside it.
Branch naming stays `<module>/prN-description` — the worktree folder name
is just a readable slug, not a new scheme.

A worktree does **not** inherit gitignored local state — `.env` files,
`node_modules/`, virtualenvs, etc. need a one-time setup per worktree (see
`scripts/setup-worktree.sh`). If your project has a single shared local
dependency (e.g. a dev database container), only one worktree should run it;
the rest point their config at that already-running instance.

### Automatic detection

The rule above depends on someone remembering to apply it before starting a
second session — exactly the kind of thing that fails under pressure.
`.claude/hooks/worktree-guard.mjs` closes that gap: a
`SessionStart`/`SessionEnd`/`PreToolUse` hook that keeps a lock file
(`.claude/.session-lock.json`, gitignored, never committed) recording which
session/PID owns the working tree.

- **`SessionStart`**: if there's no lock, create one silently. If the lock
  belongs to the same session (resume/compact/clear), refresh it silently.
  If the lock belongs to another session **and its process is still
  alive**, print a warning with the exact `git worktree add` command to
  copy/paste. If the owning process is gone (orphaned lock), reclaim it
  silently — no false alarm.
- **`PreToolUse`** (matcher `Write|Edit`): the `SessionStart` warning is
  advisory only — a session can read it and edit anyway. This hook turns it
  into a real gate: if another session is alive AND the `file_path` of the
  `Write`/`Edit` resolves inside THIS session's project root (the shared
  clone), deny the call with instructions to create a worktree. If the
  `file_path` resolves **outside** that root — e.g. an absolute path into a
  sibling worktree — allow it: that's the safe pattern (create the
  worktree, write there with an absolute path, no `cd` needed). Scope is
  deliberately limited to `Write|Edit`; it doesn't try to inspect arbitrary
  `Bash` commands (shell-based git mutations, redirections) — too fragile a
  heuristic, better to cover the common case (direct file edits) without
  false positives.
- **`SessionEnd`**: deletes the lock only if it belongs to the session
  that's ending — never touches another session's lock.

Claude Code doesn't expose the main process's real PID in the hook payload,
so detection uses `process.ppid` (the process that launched the hook
script) as an approximation — not 100% infallible, but the closest signal
available without inventing something heavier.

---

## 3. Layer 2 — The shared task book (issues as task briefs)

### Why git artifacts, not live agent-to-agent chat

Coordinating two independent workers (human or AI) doesn't require
real-time communication between them — it requires both to read and write
against the same durable, versioned source of truth. Git (commits, issues,
PRs) is already that source of truth for code; what was missing was giving
*tasks* the same treatment, instead of letting task context live only in a
chat transcript.

### The task brief

Every non-trivial task (see §5 for what counts as trivial) becomes a GitHub
issue shaped like this before implementation starts:

```markdown
## Objective
One sentence: what problem this solves, not how.

## Approach
2-4 lines: the chosen strategy (a decision, not the code).

## Files touched
Known or likely file paths.

## Done when
One verifiable completion criterion, not vague.
```

Whoever picks the task back up — the same person in a new session, a
different collaborator, or an agent session with no memory of the original
conversation — starts with `gh issue view <N>` instead of being re-briefed
from scratch. This replaces "re-explain the flow to the agent every time"
with "written once, read by anyone."

### The board (GitHub Projects) as shared state

- The agent — not the human — creates and moves cards, as standing
  behavior, not a one-off request (see `CLAUDE.md.template`).
- Before any task that plausibly touches product work, check the board
  first (`gh project item-list`) — a `SessionStart` hook can surface this
  automatically, but *deciding whether a task needs a card* stays a
  judgment call a hook can't make on its own.
- Trivial changes (a typo, a pure question, tooling-only config) don't need
  a card — see §5 for the exact line.

### Review tiers regulate how much ceremony a merge needs

| Tier | When | What it means |
|---|---|---|
| 1 | Auth, access control, tenant isolation, payments/money, or the contract of an endpoint already in production | Fresh-context review before merge — never the same session that wrote the change |
| 2 | Additive infra, no behavior change to existing surfaces | Full-diff self-review before opening the PR |
| 3 | Pure UI, docs, config | Tests + your own verification pass; no separate reviewer |

Trivial/docs-only changes need no formal review step at all.

---

## 4. The decision ladder — how a task gets routed

This is the single most important judgment call in the whole architecture,
and it runs silently before any other mechanism kicks in.

```
Does the task touch 1-3 files, have one reasonable approach, and low risk?
├── YES → direct, no intermediary. No issue, no board card, no worktree
│         (the worktree only matters if a second session is concurrently
│         active — independent of task size). Read → edit → verify →
│         commit only if asked.
└── NO → does it need a durable spec/design because the ambiguity is real
         and multiple people/sessions will build against the same
         contract?
         ├── YES → SDD (§6)
         └── NO → delegated direct: issue + task brief (§3), own branch,
                   implement, test, PR. No SDD ceremony.
```

**Worktree activation is independent of this ladder.** A one-line typo fix
made while a second session is active still needs a worktree — not because
the fix is complex, but because two sessions are touching the working tree
at the same time.

---

## 5. Layer 3 — SDD and multi-agent orchestration

### When SDD actually activates

SDD (spec-driven development) exists to remove *genuine* ambiguity before
multiple people or sessions commit to an approach — architecture decisions,
API contracts, anything where getting it wrong costs real rework. It is not
the default route (§4); use it only for substantial changes, by explicit
request or an accepted proposal — never inferred from file count, line
count, or "this feels risky."

### The SDD lifecycle

```
proposal → specs ⇄ design → tasks → apply → verify → archive
```

Each phase is a fresh-context sub-agent call. A hybrid artifact store works
well: versioned spec files (e.g. under `openspec/changes/<name>/`, or
whatever spec-file convention your SDD tooling uses) so every collaborator
sees the same spec via git, *plus* an optional session-memory tool for
cross-session recall (personal, not shared — see §7).

When one SDD change fans out into multiple parallel PRs, only the **first
PR to merge** carries the canonical copy of the spec artifacts — every
other PR references it instead of duplicating it. Two branches each
carrying their own divergent copy of the same spec will conflict on merge
even when the source code doesn't.

### Adversarial dual review (optional, high-tier changes)

For Tier 1 changes or by explicit request: two independent reviewers judge
the change blind, a synthesis step reconciles disagreement, and a fix agent
applies only the confirmed fixes — at most two bounded fix/re-review
rounds, never an open loop.

### Sub-agent types worth having

| Agent | Role |
|---|---|
| Read-only explorer | Fast code search — files, symbols, "where is X" |
| General-purpose | Multi-step research or implementation, full tool access |
| Planner | Architecture/implementation planning, no file writes |
| SDD phase agents | One per SDD phase (explore/propose/spec/design/tasks/apply/verify/archive) |
| Adversarial review agents | Blind dual-judge review + fix agent |
| Focused review lenses | Risk, readability, reliability, resilience, etc. |

Add new agent types only when a **narrow, well-defined, recurring** task
justifies it — not as a general "more AI leverage" strategy. Most teams
need fewer agent types than they think; the leverage is using the ones you
have consistently, not multiplying them.

### Multi-agent orchestration — when parallelism earns its cost

Fan-out/parallel orchestration (multiple sub-agents in a pipeline or in
parallel: research fan-out, multi-lens adversarial review, judge panels)
is justified when a task has **more than one independent angle worth
comparing** — not simply because it's big. A single, well-scoped delegated
sub-agent is the default; reach for parallel orchestration only when
several independent perspectives running at once would change the result,
not just the ceremony.

---

## 6. Personal memory vs. shared truth — the rule that must never blur

A persistent-memory tool (if you use one) is typically local to the machine
it runs on. It gives one collaborator's own sessions continuity across
compactions/restarts. It does **not** sync between collaborators — there is
no server behind it.

**Anything another collaborator needs to know — architecture decisions, API
contracts, workflow or convention changes — must be written to a
git-tracked file in the same session it's decided.** This is a mandatory
rule (see `CLAUDE.md.template`, "Decision persistence rule"), and this
document plus any SDD spec folder are both instances of that one rule.

---

## 7. Instruction-file map

| File | Scope | Loaded by |
|---|---|---|
| `CLAUDE.md` (root) | Team workflow: worktrees, board rules, branch/PR conventions, review tiers | Auto-loaded by Claude Code at repo root |
| `<subdir>/CLAUDE.md` (optional, per stack) | Stack-specific conventions, hard rules | Auto-loaded when working under that subdirectory |
| `docs/architecture.md` (this file) | The AI-first architecture itself | Read when reasoning about workflow, not product |
| `~/.claude/CLAUDE.md` (global, per collaborator) | Personal Claude Code tool contract: delegation routing, persona, pointers to shared tooling | Not in this repo — machine-local |

These file names generally can't be changed (Claude Code discovers
`CLAUDE.md` by exact name at each folder level), but they're distinguished
by their opening heading once opened.

---

## 8. Tools this architecture runs on

See `TOOLS.md` for the install/check table. In short: Claude Code +
optional gentle-ai (SDD/review orchestration) + optional structural
code-intelligence indexing are the load-bearing pieces; persistent-memory
and style-enforcement plugins are valuable but not required for the
worktree/board/review-tier mechanics to work.

No RAG pipeline, no extra agent framework, and no vector database are part
of this architecture by default. Don't reintroduce one without a concrete
gap that structural code intelligence and spec files don't already cover.

---

## 9. Keep this doc in sync

Update this document in the same change that touches any mechanism it
describes — the same "decision persistence" rule that governs everything
else here.
