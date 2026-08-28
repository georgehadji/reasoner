#!/usr/bin/env bash
# PostToolUse on Write|Edit. Observability only: stderr is shown to Claude, which fixes it.
# Scoped to ui-next/. globals.css is exempt — Tailwind v4 declares the theme there
# (CSS-native config, no tailwind.config.ts), so raw values are correct in that file.
set -uo pipefail
. "$(dirname "$0")/_lib.sh"
INPUT="$(cat)"
FILE="$(extract_file_path "$INPUT")"

[ -f "$FILE" ] || exit 0
case "$FILE" in
  */ui-next/*|ui-next/*) ;;
  *) exit 0 ;;
esac
case "$FILE" in
  *tokens.css|*globals.css) exit 0 ;;
  *.css|*.tsx|*.jsx|*.astro|*.vue|*.svelte) ;;
  *) exit 0 ;;
esac

HITS="$(grep -nE '#[0-9a-fA-F]{3,8}\b|rgba?\(|[0-9]+px' "$FILE" | grep -vE '1px|0px|var\(--' | head -20 || true)"
if [ -n "$HITS" ]; then
  {
    echo "TOKEN DRIFT in $FILE — raw design values found. Replace with var(--…) from ui-next/src/styles/tokens.css:"
    echo "$HITS"
  } >&2
fi
exit 0
