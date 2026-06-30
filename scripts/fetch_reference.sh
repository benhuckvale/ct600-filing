#!/bin/sh
# Materialise the cybermaggedon/ct600 worked examples into reference/ct600/.
#
# AGENTS.md and TROUBLESHOOTING.md refer to reference/ct600/accts.html and
# ct.html (worked iXBRL examples). That directory is gitignored (not vendored
# here) — this script recreates it on demand. Run: `pdm run fetch-reference`.
#
# Pinned to a specific commit so the worked examples don't drift under us. To
# bump, change PIN and re-run.
set -e

REPO_URL="https://github.com/cybermaggedon/ct600"
PIN="b7dd2f8c998ba5cb32f60b6e3ebc5daf35f26d5f"
DEST="$(git rev-parse --show-toplevel)/reference/ct600"

if [ -d "$DEST/.git" ]; then
    echo "reference/ct600 present at $(git -C "$DEST" rev-parse --short HEAD); checking out pin..."
    git -C "$DEST" fetch --quiet origin || true
else
    echo "Cloning $REPO_URL into reference/ct600 ..."
    git clone --quiet "$REPO_URL" "$DEST"
fi

git -C "$DEST" checkout --quiet "$PIN"
echo "reference/ct600 ready at ${PIN%${PIN#???????}} ($REPO_URL)"
echo "  worked examples: reference/ct600/accts.html, reference/ct600/ct.html"
