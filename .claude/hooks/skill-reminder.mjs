#!/usr/bin/env node
// PostToolUse hook (Write|Edit): the first time in a session that a source
// file in a given category is touched, reminds which installed project
// skills and conventions apply to it — same problem the SessionStart
// board-context hook solves for "check the board before starting", applied
// to "actually consult the architecture/pattern rules while coding" instead
// of only when someone remembers to ask.
//
// Fires at most once per category per session, tracked via a small marker
// file keyed by session_id under the OS temp dir — so a long editing
// session doesn't get one reminder per keystroke, just one early enough to
// matter before a coding streak happens.
//
// ---- CONFIG — edit CATEGORIES for your project ----------------------------
// Each entry: a name, a regex tested against the normalized (forward-slash)
// file path, a short checklist of conventions to surface, and paths to the
// full skill files (if any) for further reading. Add/remove entries freely
// — this file ships with zero entries configured; nothing fires until you
// fill this in.
const CATEGORIES = [
  // Example — copy/adapt per stack in your project:
  // {
  //   name: "frontend",
  //   test: /\/frontend\/.*\.(tsx|ts)$/,
  //   checklist: [
  //     "container-presentational: pages delegate state/effects to a colocated hook",
  //     "split a component past ~300 lines into a private _components/ folder",
  //     "no `any`; prefer `import type` for type-only imports",
  //   ],
  //   skills: ["frontend/.claude/skills/solid-principles/SKILL.md"],
  // },
  // {
  //   name: "backend",
  //   test: /\/backend\/.*\.py$/,
  //   checklist: [
  //     "router only parses/validates, service holds logic, repository only persists",
  //     "match architecture pattern to real complexity — don't reach for DDD on plain CRUD",
  //   ],
  //   skills: ["backend/.claude/skills/architecture-patterns/SKILL.md"],
  // },
];
// -----------------------------------------------------------------------

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

function readStdin() {
  return new Promise((resolve) => {
    let data = "";
    process.stdin.on("data", (chunk) => {
      data += chunk;
    });
    process.stdin.on("end", () => resolve(data));
  });
}

function categoryFor(filePath) {
  const normalized = filePath.replace(/\\/g, "/");
  if (normalized.includes("/node_modules/") || normalized.includes("/.git/")) {
    return null;
  }
  return CATEGORIES.find((c) => c.test.test(normalized)) ?? null;
}

function alreadyReminded(sessionId, categoryName) {
  const markerPath = join(tmpdir(), `ai-workflow-starter-kit-skill-reminder-${sessionId}.json`);
  let seen = {};
  if (existsSync(markerPath)) {
    try {
      seen = JSON.parse(readFileSync(markerPath, "utf8"));
    } catch {
      seen = {};
    }
  }
  if (seen[categoryName]) {
    return true;
  }
  seen[categoryName] = true;
  mkdirSync(tmpdir(), { recursive: true });
  writeFileSync(markerPath, JSON.stringify(seen));
  return false;
}

if (CATEGORIES.length === 0) {
  process.exit(0); // not configured for this project yet
}

const raw = await readStdin();
let payload;
try {
  payload = JSON.parse(raw || "{}");
} catch {
  process.exit(0);
}

const filePath = payload?.tool_input?.file_path;
const sessionId = payload?.session_id ?? "unknown-session";
if (!filePath) {
  process.exit(0);
}

const category = categoryFor(filePath);
if (!category || alreadyReminded(sessionId, category.name)) {
  process.exit(0);
}

const checklistText = category.checklist.map((item, i) => `${i + 1}. ${item}`).join("\n");

console.log(
  JSON.stringify({
    hookSpecificOutput: {
      hookEventName: "PostToolUse",
      additionalContext:
        `Editing ${category.name} code — project conventions/skills checklist for this file and any others you touch for the rest of this session:\n${checklistText}\n\n` +
        (category.skills?.length ? `Full skills: ${category.skills.join(", ")}. ` : "") +
        "(One reminder per category per session — won't repeat, but the checklist still applies.)",
    },
  }),
);
