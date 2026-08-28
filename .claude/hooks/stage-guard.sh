#!/usr/bin/env bash
# PreToolUse on Write|Edit. Exit 2 blocks the call; stderr goes back to Claude.
# Inert until spec/.gate-enabled exists.
#
# Reasoner scoping: this repo is an application, not a marketing site. The
# frontend lives in ui-next/; src/reasoner/** is the Python backend and must
# never be gated on design tokens. Match ui-next paths only.
set -uo pipefail
. "$(dirname "$0")/_lib.sh"
INPUT="$(cat)"

ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
[ -f "$ROOT/spec/.gate-enabled" ] || exit 0
FILE="$(extract_file_path "$INPUT")"

TOKENS="$ROOT/ui-next/src/styles/tokens.css"
ART="$ROOT/spec/art-direction.md"

case "$FILE" in
  */ui-next/src/*|ui-next/src/*)
    case "$FILE" in
      */styles/tokens.css) exit 0 ;;
    esac
    if [ ! -s "$ART" ] \
       || grep -q 'Not written yet' "$ART" 2>/dev/null \
       || ! grep -q '[^[:space:]]' "$TOKENS" 2>/dev/null; then
      echo "BLOCKED: spec/art-direction.md and ui-next/src/styles/tokens.css must exist and be non-empty before writing $FILE. Run /art-direction first." >&2
      exit 2
    fi
    ;;
esac
exit 0
