#!/usr/bin/env node
// SessionStart hook: surfaces the current GitHub Projects board state so
// "check the board before starting a task" doesn't depend on remembering to
// run it manually.
//
// ---- CONFIG — edit these two constants for your project -------------------
const PROJECT_NUMBER = process.env.GH_PROJECT_NUMBER || "<PLACEHOLDER: project number, e.g. 1>";
const OWNER = process.env.GH_PROJECT_OWNER || "<PLACEHOLDER: github org or user, e.g. my-org>";
// Both can instead be set as env vars (GH_PROJECT_NUMBER / GH_PROJECT_OWNER)
// if you'd rather not hardcode them here — env vars win when set.
// -----------------------------------------------------------------------

import { execFileSync } from "node:child_process";

function fetchBoardItems() {
  try {
    const raw = execFileSync(
      "gh",
      [
        "project",
        "item-list",
        PROJECT_NUMBER,
        "--owner",
        OWNER,
        "--limit",
        "200",
        "--format",
        "json",
        "--jq",
        '[.items[] | {number: (.content.number // null), title, status: (.status // "No status")}]',
      ],
      { encoding: "utf8", timeout: 15000 },
    );
    return JSON.parse(raw || "[]");
  } catch {
    return null;
  }
}

function checkHooksPath() {
  try {
    const configured = execFileSync("git", ["config", "--get", "core.hooksPath"], {
      encoding: "utf8",
      timeout: 5000,
    }).trim();
    // PLACEHOLDER: adjust if your project's local git hooks live somewhere
    // other than ".githooks".
    return configured === ".githooks";
  } catch {
    return false;
  }
}

if (PROJECT_NUMBER.startsWith("<PLACEHOLDER") || OWNER.startsWith("<PLACEHOLDER")) {
  console.log(
    JSON.stringify({
      hookSpecificOutput: {
        hookEventName: "SessionStart",
        additionalContext:
          "board-context.mjs is not configured yet — set PROJECT_NUMBER/OWNER at the top of " +
          ".claude/hooks/board-context.mjs (or the GH_PROJECT_NUMBER/GH_PROJECT_OWNER env vars) " +
          "to enable the GitHub Projects board summary at session start.",
      },
    }),
  );
  process.exit(0);
}

const items = fetchBoardItems();
const hooksPathActive = checkHooksPath();

let context;
if (items === null) {
  context =
    `Could not read GitHub Projects board #${PROJECT_NUMBER} (${OWNER}) at session start ` +
    "(gh not authenticated, no network, or command unavailable). Verify manually with " +
    `\`gh project item-list ${PROJECT_NUMBER} --owner ${OWNER}\` before creating a new issue ` +
    "or starting product work.";
} else if (items.length === 0) {
  context = `GitHub Projects board #${PROJECT_NUMBER} (${OWNER}) is empty.`;
} else {
  const lines = items
    .map((item) => `- #${item.number ?? "?"} ${item.title} [${item.status}]`)
    .join("\n");
  context =
    `GitHub Projects board #${PROJECT_NUMBER} (${OWNER}) at session start:\n${lines}\n\n` +
    "Before creating a new issue or starting any product task the user asks for, check whether a card already covers it.";
}

if (!hooksPathActive) {
  context +=
    "\n\nNote: core.hooksPath is not configured on this machine (`git config core.hooksPath .githooks`) — " +
    "local pre-push checks won't run before your pushes.";
}

console.log(
  JSON.stringify({
    hookSpecificOutput: {
      hookEventName: "SessionStart",
      additionalContext: context,
    },
  }),
);
