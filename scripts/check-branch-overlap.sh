#!/usr/bin/env bash
# Automates the "does origin/main overlap with my unpushed commits?" check
# from CLAUDE.md.template ("Before every push" / "Rebase-before-merge for
# stacked/parallel PR chains") — replaces comparing diffs by eye.
#
# Usage (from your feature branch, before pushing or merging):
#   ./scripts/check-branch-overlap.sh
set -e

# PLACEHOLDER: change "origin/main" below if your default branch has a
# different name (e.g. "origin/master", "origin/develop").
git fetch origin --quiet

base="$(git merge-base HEAD origin/main)"
remote_new="$(git rev-list "$base"..origin/main)"

if [ -z "$remote_new" ]; then
  echo "origin/main has no new commits since your base — push directly, nothing to check."
  exit 0
fi

echo "New commits on origin/main since your base ($base):"
git log --oneline "$base"..origin/main
echo

remote_files="$(git diff --name-only "$base" origin/main)"
local_files="$(git diff --name-only "$base" HEAD)"
overlap="$(comm -12 <(echo "$remote_files" | sort) <(echo "$local_files" | sort))"

if [ -n "$overlap" ]; then
  echo "OVERLAP — these files changed on both sides:"
  echo "$overlap"
  echo
  echo "STOP: read both diffs in full before touching anything; resolve the conflict"
  echo "deliberately during the rebase. Never 'git push --force' over someone else's work."
  exit 1
fi

echo "No file overlap — safe to: git rebase origin/main && git push"
