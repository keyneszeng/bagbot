#!/usr/bin/env bash
# Install the bagbot skill into every agent skills directory found.
#
# Supported targets (skipped if not present):
#   - Claude Code:            ~/.claude/skills/bagbot
#   - Codex CLI:              ~/.codex/skills/bagbot
#   - Gemini CLI:             ~/.gemini/skills/bagbot
#   - DSH/Open-source agents: ~/.agents/skills/bagbot
#   - Cursor:                 ~/.cursor/skills/bagbot
#
# Usage:
#   bash scripts/install_skill.sh          # install everywhere found
#   SKILL_DEST=~/.claude/skills bash scripts/install_skill.sh   # single target
#
# What it installs: the whole skills/bagbot/ tree (SKILL.md, scripts,
# examples, references) as a symlink if possible, else a copy.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_SRC="$HERE/../skills/bagbot"
SKILL_NAME="bagbot"

[[ -f "$SKILL_SRC/SKILL.md" ]] || { echo "skill source not found at $SKILL_SRC" >&2; exit 1; }

install_to() {
  local dest="$1"
  if [[ "$dest" == */skills ]]; then
    dest="$dest/$SKILL_NAME"
  fi
  mkdir -p "$(dirname "$dest")"
  if [[ -e "$dest" || -L "$dest" ]]; then
    echo "  • $dest  (exists — relinking)"
    rm -rf "$dest"
  fi
  # Prefer symlink so the repo stays the single source of truth.
  ln -s "$SKILL_SRC" "$dest" && echo "  ✓ symlinked $dest -> $SKILL_SRC" \
    || { cp -R "$SKILL_SRC" "$dest" && echo "  ✓ copied   $dest"; }
}

echo "BagBot skill installer"
echo "  source: $SKILL_SRC"
echo

if [[ -n "${SKILL_DEST:-}" ]]; then
  echo "Installing to \$SKILL_DEST:"
  install_to "$SKILL_DEST"
  echo
  echo "Done."
  exit 0
fi

found=0
for home in "$HOME/.claude" "$HOME/.codex" "$HOME/.gemini" "$HOME/.agents" "$HOME/.cursor"; do
  base="${home}/skills"
  if [[ -d "$home" ]]; then
    [[ $found -eq 0 ]] && echo "Found agent homes — installing:"
    install_to "$base"
    found=1
  fi
done

if [[ $found -eq 0 ]]; then
  echo "No supported agent homes found under \$HOME."
  echo "Pick one explicitly, e.g.:"
  echo "  SKILL_DEST=~/.claude/skills bash $0"
  exit 1
fi

echo
echo "Installed 'bagbot' skill. To verify:"
echo "  ls -l ~/.claude/skills/bagbot/SKILL.md"
