#!/usr/bin/env bash
# SessionStart. Plain stdout is injected into context, so this is the cheapest way to
# put pipeline state in front of the model on every session.
#
# Reasoner scoping: this repo is an application, not a client marketing site. Only
# /adopt -> /art-direction -> /build -> /qa-gate apply. message-map, query-map and
# growth-plan presuppose a buyer and a funnel and are intentionally not tracked here.
set -uo pipefail
ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
cd "$ROOT" 2>/dev/null || exit 0

echo "## Studio pipeline state (scope: ui-next/ only)"
for f in brief art-direction ia qa-report; do
  p="spec/$f.md"
  if [ -s "$p" ] && ! grep -q 'Not written yet' "$p" 2>/dev/null; then
    echo "- $f: written ($(wc -l < "$p" | tr -d ' ') lines)"
  else
    echo "- $f: NOT WRITTEN"
  fi
done

if [ -s "ui-next/src/styles/tokens.css" ]; then
  echo "- tokens.css: present (ui-next/src/styles/tokens.css)"
else
  echo "- tokens.css: MISSING"
fi

if [ -f "spec/.gate-enabled" ]; then
  echo "- write gate: ARMED — writes to ui-next/src/** require art-direction.md + tokens.css"
else
  echo "- write gate: inert (no spec/.gate-enabled) — nothing is blocked"
fi
echo "- backend src/reasoner/** is never gated by this pipeline."
echo "Next stage is the first NOT WRITTEN artifact in that order."
