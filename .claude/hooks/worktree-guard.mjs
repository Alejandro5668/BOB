#!/usr/bin/env node
// SessionStart/SessionEnd/PreToolUse hook: detects a second Claude Code
// session already active against this same working tree. SessionStart/End
// warn instead of letting both sessions silently share one HEAD/working
// tree/index (see docs/architecture.md, "Layer 1 — workspace isolation").
// Claude Code does not expose the running process's PID or a cross-session
// registry, so this implements its own lock file:
// `.claude/.session-lock.json` (gitignored, per-machine, never committed).
//
// Wiring: registered for "SessionStart", "SessionEnd", AND "PreToolUse"
// (matcher "Write|Edit") in .claude/settings.json, all pointing at this
// same file — it branches on `hook_event_name` from the stdin payload.
//
// Why PreToolUse exists (not just SessionStart): the SessionStart warning
// alone is advisory only — a session can read it and still go on to edit
// files directly in the shared clone. PreToolUse turns the warning into an
// actual gate at the moment of risk: it denies Write/Edit calls whose
// target file resolves inside THIS session's project root while another
// session's lock is live, but allows edits whose target resolves elsewhere
// (e.g. an absolute path into a sibling `../<repo>-<slug>` worktree) —
// that's the documented escape hatch: create a worktree and write into it,
// no `cd` required since Edit/Write take absolute paths.
//
// Liveness check uses `process.ppid` (the PID that spawned this hook
// script) as a best-effort stand-in for "the Claude Code process that owns
// this lock is still running" — Claude Code's hook payload doesn't include
// its own PID directly, so this is the closest available signal, not a
// guaranteed-exact one. A stale lock (owner process no longer alive) is
// silently reclaimed rather than treated as a false collision.
import { existsSync, readFileSync, writeFileSync, unlinkSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { resolve, sep } from "node:path";
import { join } from "node:path";

const LOCK_PATH = join(process.cwd(), ".claude", ".session-lock.json");

function readStdin() {
  return new Promise((resolve) => {
    let data = "";
    process.stdin.on("data", (chunk) => {
      data += chunk;
    });
    process.stdin.on("end", () => resolve(data));
  });
}

function readLock() {
  if (!existsSync(LOCK_PATH)) return null;
  try {
    return JSON.parse(readFileSync(LOCK_PATH, "utf8"));
  } catch {
    return null;
  }
}

function writeLock(lock) {
  writeFileSync(LOCK_PATH, JSON.stringify(lock, null, 2));
}

function removeLock() {
  try {
    unlinkSync(LOCK_PATH);
  } catch {
    // already gone — nothing to clean up
  }
}

function isPidAlive(pid) {
  if (!pid) return false;
  try {
    if (process.platform === "win32") {
      const out = execFileSync("tasklist", ["/FI", `PID eq ${pid}`, "/FO", "CSV", "/NH"], {
        encoding: "utf8",
        timeout: 5000,
      });
      // A real match is a CSV row starting with a quoted field
      // (`"ProcessName","PID",...`). When nothing matches, tasklist still
      // writes a non-empty "no tasks match" message (localized on some
      // Windows installs), so a plain length-check on stdout is not
      // reliable — check for the quoted-CSV shape instead.
      return out.trim().startsWith('"');
    }
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

function suggestedSlug(cwd) {
  const base = cwd.split(/[\\/]/).filter(Boolean).pop() || "repo";
  return `../${base}-worktree`;
}

function emit(hookEventName, additionalContext) {
  if (!additionalContext) {
    process.exit(0);
  }
  console.log(
    JSON.stringify({
      hookSpecificOutput: { hookEventName, additionalContext },
    }),
  );
}

const raw = await readStdin();
let payload;
try {
  payload = JSON.parse(raw || "{}");
} catch {
  process.exit(0);
}

const eventName = payload?.hook_event_name;
const sessionId = payload?.session_id ?? "unknown-session";
const cwd = payload?.cwd ?? process.cwd();

if (eventName === "PreToolUse") {
  const lock = readLock();
  // No lock, it's our own lock, or the owner process is dead: nothing to
  // guard against — same liveness check SessionStart already uses.
  if (!lock || lock.sessionId === sessionId || !isPidAlive(lock.pid)) {
    process.exit(0);
  }

  const filePath = payload?.tool_input?.file_path;
  if (!filePath) process.exit(0); // matcher is Write|Edit; both always carry file_path

  const projectRoot = resolve(cwd);
  const target = resolve(filePath);
  const isInsideThisClone = target === projectRoot || target.startsWith(projectRoot + sep);

  if (!isInsideThisClone) {
    // Target resolves outside this session's project root (e.g. an absolute
    // path into a sibling worktree) — exactly the safe pattern, allow it.
    process.exit(0);
  }

  console.log(
    JSON.stringify({
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "deny",
        permissionDecisionReason:
          "Another Claude Code session is still active in this same clone " +
          `(${cwd}) — blocked to avoid stepping on its checkout/commits (see ` +
          "docs/architecture.md, Layer 1). Create your own worktree and write " +
          "there (you can pass the worktree's absolute path straight to " +
          "Edit/Write, no 'cd' needed):\n\n" +
          `  git worktree add ${suggestedSlug(cwd)} <module>/prN-description\n`,
      },
    }),
  );
  process.exit(0);
}

if (eventName === "SessionEnd") {
  const lock = readLock();
  if (lock?.sessionId === sessionId) {
    removeLock();
  }
  process.exit(0);
}

// SessionStart (source: "startup" | "resume" | "clear" | "compact" | "fork")
const lock = readLock();
const pid = process.ppid;

if (!lock) {
  writeLock({ sessionId, pid, cwd, startedAt: Date.now() });
  process.exit(0);
}

if (lock.sessionId === sessionId) {
  // Same session re-entering SessionStart (resume/compact/clear) — refresh, no warning.
  writeLock({ sessionId, pid, cwd, startedAt: lock.startedAt ?? Date.now() });
  process.exit(0);
}

if (!isPidAlive(lock.pid)) {
  // Stale lock — the previous owner is gone (crashed, force-closed, or a
  // SessionEnd hook never fired). Reclaim silently, this is not a real collision.
  writeLock({ sessionId, pid, cwd, startedAt: Date.now() });
  process.exit(0);
}

// Another session's lock is present AND its process is still alive: real concurrency.
const slug = suggestedSlug(cwd);
const branchPlaceholder = "<module>/prN-description";
emit(
  "SessionStart",
  "WARNING — another Claude Code session appears to be active right now in this same directory " +
    `(${cwd}). Both sessions working the same working tree can step on each other's uncommitted ` +
    "checkouts/commits (see docs/architecture.md, Layer 1). A PreToolUse hook will block any " +
    "Write/Edit inside this clone while the other session stays active. Before touching branches " +
    "or files, create your own worktree for THIS session:\n\n" +
    `  git worktree add ${slug} ${branchPlaceholder}\n\n` +
    "and keep working from that folder instead of this one. If you're sure the other session " +
    "already ended (an orphaned lock), you can ignore this warning — it will self-clean next time.",
);
