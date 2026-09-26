#!/usr/bin/env sh
# Install or update the Higgsfield skill for Claude Code (default) or Codex (--codex).
set -e
REPO="https://github.com/Koushik890/higgsfield-api-skill.git"
if [ "$1" = "--codex" ]; then
  DEST="${CODEX_HOME:-$HOME/.codex}/skills/higgsfield"
else
  DEST="$HOME/.claude/skills/higgsfield"
fi

if [ -d "$DEST/.git" ]; then
  git -C "$DEST" pull --ff-only
else
  mkdir -p "$(dirname "$DEST")"
  git clone "$REPO" "$DEST"
fi

CONF="$HOME/.config/higgsfield/.env"
if [ ! -f "$CONF" ]; then
  mkdir -p "$(dirname "$CONF")"
  cp "$DEST/.env.example" "$CONF"
  chmod 600 "$CONF"
  echo "Created $CONF - add your API key there."
fi
echo "Installed to $DEST. Start a new agent session to use it."
