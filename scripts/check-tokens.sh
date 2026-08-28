#!/usr/bin/env bash
# Fails when ui-next component source carries raw design values instead of tokens.
#
# Scope: ui-next/src only. src/reasoner/** is the Python backend and is not part of
# the design pipeline. globals.css is exempt — Tailwind v4 declares the theme there
# CSS-natively (there is no tailwind.config.ts), so raw values are correct in that file.
set -uo pipefail
STATUS=0
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FILES="$(find "$ROOT/ui-next/src" -type f \( -name '*.css' -o -name '*.tsx' -o -name '*.jsx' \) 2>/dev/null | grep -vE 'tokens\.css|globals\.css' || true)"
[ -z "$FILES" ] && { echo "check-tokens: no ui-next source files found"; exit 0; }
for f in $FILES; do
  HITS="$(grep -nE '#[0-9a-fA-F]{3,8}\b|rgba?\(|oklch\(' "$f" | grep -v 'var(--' || true)"
  if [ -n "$HITS" ]; then echo "TOKEN DRIFT ${f#$ROOT/}"; echo "$HITS"; STATUS=1; fi
done
exit $STATUS
