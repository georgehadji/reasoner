---
description: Reverse-engineer an existing website into the spec/ artifacts so the pipeline can take over. Use once, on a project that was built before this system was adopted.
disable-model-invocation: true
---

## Scope for this repository

Reasoner is an **application**, not a client marketing site. The frontend under audit is
`ui-next/` (Next.js 16 / React 19 / Tailwind CSS v4). `src/reasoner/**` is the Python
backend and is **out of scope for every stage of this pipeline** — do not census it, do
not propose changes to it, do not count its files.

Tailwind v4 has no `tailwind.config.ts`; the theme is declared CSS-natively in
`ui-next/src/app/globals.css`. That file is the current de-facto token source.

## Current source signals
```!
cd "${CLAUDE_PROJECT_DIR}/ui-next" 2>/dev/null || exit 0
echo "--- routes/pages ---"; ls -R src/app src/components 2>/dev/null | head -60 || true
echo "--- colours in use ---"; grep -rhoE '#[0-9a-fA-F]{3,8}\b|oklch\([^)]*\)|rgba?\([^)]*\)' src 2>/dev/null | sort | uniq -c | sort -rn | head -30 || true
echo "--- font families ---"; grep -rhoE 'font-family:[^;]*|--font[a-z-]*:[^;]*' src 2>/dev/null | sort -u | head -20 || true
echo "--- spacing values ---"; grep -rhoE '\b[0-9]+(\.[0-9]+)?(px|rem)\b' src 2>/dev/null | sort | uniq -c | sort -rn | head -30 || true
echo "--- globals.css theme block ---"; sed -n '1,80p' src/app/globals.css 2>/dev/null || true
echo "--- deps ---"; sed -n '1,60p' package.json 2>/dev/null || true
```

## Task
Do not change a single line of application code in this stage. You are producing an
honest description of what exists, so later stages have something to work from.

Write, in this order:

1. `spec/brief.md` — what this application is, who operates it, the primary action a user
   takes in the UI, and the proof/claims the interface already makes. Everything you
   cannot know from the code goes under OPEN QUESTIONS as a one-line question. Do not fill
   gaps with plausible guesses; an adopted brief with twelve open questions is correct,
   one with none is fiction.

2. `spec/art-direction.md` — the direction that is *actually* in `ui-next/` today:
   the real palette (from the colour census above, consolidated into named roles), the
   real typefaces and their loading strategy, the real spacing rhythm, the real layout
   system, and whether there is a signature element or none. Then a verdict section:
   walk `spec/banlist.md` item by item against the current UI and list every hit.
   Finish with a genericness score out of 10 and the three changes with the highest
   distinctiveness-per-hour-of-work.

3. `ui-next/src/styles/tokens.css` — CSS custom properties derived from the values
   actually in use, consolidated: near-duplicate greys collapse into one token, a
   13-value spacing soup collapses onto a scale. Reconcile against the existing
   `globals.css` theme block rather than duplicating it — state explicitly which tokens
   are new and which already exist there. Add a comment block listing every raw value you
   folded and what it maps to, so the migration is mechanical later.

4. `spec/ia.md` — the route and component-template inventory as it exists in `ui-next/`,
   plus a column marking each KEEP / MERGE / CUT with the reason.

Then create the marker file that arms the write gate:

```
touch spec/.gate-enabled
```

The gate is scoped to `ui-next/src/**` only; arming it never blocks backend work.

Report at the end: what you could not determine from the code alone, and which stage
should run next given what you found.
