#!/usr/bin/env bash
# Seeds a freshly-created `git worktree add` directory with the local state
# it does NOT get for free from git (gitignored .env files, dependency
# installs). Copying dependency directories from the main clone instead of
# installing from scratch, then reconciling against the same lockfile, turns
# a multi-minute clean install into a few seconds.
#
# Usage (from the main clone, after `git worktree add ../repo-slug ...`):
#   ./scripts/setup-worktree.sh ../repo-slug
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 <path-to-worktree>" >&2
  exit 1
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target="$(cd "$1" && pwd)"

if [ "$target" = "$repo_root" ]; then
  echo "ERROR: target is the main clone itself ($repo_root) — pass a worktree path." >&2
  exit 1
fi

echo "== setup-worktree: seeding $target from $repo_root =="

# ---------------------------------------------------------------------------
# CUSTOMIZE THIS SECTION per project. Below are the two common cases from the
# reference project this kit was extracted from — uncomment/adapt what your
# stack needs, delete what it doesn't. Add one block per app/package.
# ---------------------------------------------------------------------------

# --- env files (gitignored, never come from git) ---------------------------
# PLACEHOLDER: list every gitignored .env file your project needs per app.
# if [ -f "$repo_root/backend/.env" ] && [ ! -f "$target/backend/.env" ]; then
#   cp "$repo_root/backend/.env" "$target/backend/.env"
#   echo "copied backend/.env"
# fi
# if [ -f "$repo_root/frontend/.env.local" ] && [ ! -f "$target/frontend/.env.local" ]; then
#   cp "$repo_root/frontend/.env.local" "$target/frontend/.env.local"
#   echo "copied frontend/.env.local"
# fi

# --- Node app: seed node_modules, then reconcile with npm install ----------
# `npm install` (not `npm ci`) on purpose: ci wipes node_modules and
# reinstalls from scratch every time, which is exactly the slow path this
# script exists to avoid. Seeding with a copy that already matches the same
# lockfile means `npm install` only has to reconcile the diff (normally
# none), not build the whole tree.
# robocopy's exit codes 0-7 all mean success (bitmask of "files copied" /
# "extra files" flags) — only 8+ is a real failure. Under `set -e`, a plain
# non-zero exit would abort the script on robocopy's NORMAL codes, so the
# `|| rc=$?` form is required.
# PLACEHOLDER: replace "frontend" below with your app directory, or repeat
# the block per app in a monorepo.
# if [ -d "$repo_root/frontend/node_modules" ]; then
#   echo "seeding frontend/node_modules (robocopy)..."
#   mkdir -p "$target/frontend/node_modules"
#   rc=0
#   robocopy "$(cygpath -w "$repo_root/frontend/node_modules")" \
#     "$(cygpath -w "$target/frontend/node_modules")" \
#     /E /NFL /NDL /NJH /NJS /NC /NS /MT:8 >/dev/null || rc=$?
#   if [ "$rc" -ge 8 ]; then
#     echo "ERROR: robocopy failed copying node_modules (exit $rc)" >&2
#     exit 1
#   fi
# fi
# (cd "$target/frontend" && npm install)

# On macOS/Linux, replace the robocopy block with:
#   cp -a "$repo_root/frontend/node_modules" "$target/frontend/node_modules"

# --- Python app: seed a virtualenv, then reconcile with poetry/pip ---------
# PLACEHOLDER: adapt to your dependency manager (poetry, pip+venv, uv, ...).
# if [ -d "$repo_root/backend/.venv" ]; then
#   echo "seeding backend/.venv (robocopy)..."
#   mkdir -p "$target/backend/.venv"
#   rc=0
#   robocopy "$(cygpath -w "$repo_root/backend/.venv")" \
#     "$(cygpath -w "$target/backend/.venv")" \
#     /E /NFL /NDL /NJH /NJS /NC /NS /MT:8 >/dev/null || rc=$?
#   if [ "$rc" -ge 8 ]; then
#     echo "ERROR: robocopy failed copying .venv (exit $rc)" >&2
#     exit 1
#   fi
# fi
# (cd "$target/backend" && poetry install --no-interaction --quiet)

# --- suggest a dev-server port that won't collide with other worktrees -----
# Main clone stays on its default port (e.g. 3000). Each worktree beyond it
# gets default+N, N = its 1-based position in `git worktree list` (excluding
# the main clone). `git worktree list` prints native Windows paths on
# Windows; `pwd` under git-bash prints MSYS POSIX paths — normalize both
# through `cygpath -u` before comparing, or the main-clone exclusion silently
# fails. Skip the cygpath calls entirely on macOS/Linux.
# PLACEHOLDER: change 3000 to your project's actual default dev port.
base_port=3000
mapfile -t other_worktrees < <(git -C "$repo_root" worktree list --porcelain \
  | grep '^worktree ' | cut -d' ' -f2- | while read -r p; do
      if command -v cygpath >/dev/null 2>&1; then cygpath -u "$p"; else echo "$p"; fi
    done \
  | grep -vFx "$repo_root")
port=$base_port
for i in "${!other_worktrees[@]}"; do
  if [ "${other_worktrees[$i]}" = "$target" ]; then
    port=$((base_port + 1 + i))
    break
  fi
done

echo "== setup-worktree: done =="
echo "Suggested dev port for this worktree: $port"
echo "(Fill in the actual dev-server start command for your stack, e.g.:"
echo "  npm run dev -- -p $port   from $target/frontend)"
