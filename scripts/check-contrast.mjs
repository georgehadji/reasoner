#!/usr/bin/env node
/**
 * check-contrast.mjs — WCAG AA gate for ui-next/src/styles/tokens.css
 *
 * Why this exists: the previous design system annotated every ink token with a
 * contrast ratio measured against --bg and only --bg. Measured against the eight
 * OTHER grounds the same ink actually renders on, it shipped seven sub-AA pairs,
 * and --border-strong failed the WCAG 1.4.11 criterion its own comment cited.
 *
 * Annotations in a comment are not a check. This is the check.
 *
 * Every ink is measured against every ground it is LEGAL on, in both themes.
 * A token may declare fewer legal grounds (see --text-subtle) — that is a real
 * restriction of the system, not a failure, so it is declared here in code
 * rather than discovered at review time.
 *
 * Usage:  node scripts/check-contrast.mjs [--verbose]
 * Exit:   0 all pass · 1 any AA failure · 2 could not parse
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const TOKENS = join(ROOT, 'ui-next', 'src', 'styles', 'tokens.css');
const VERBOSE = process.argv.includes('--verbose');

const AA_TEXT = 4.5; // WCAG 1.4.3 normal text
const AA_UI = 3.0; // WCAG 1.4.11 non-text (borders, focus rings)

/* ---- colour math ---------------------------------------------------- */

const srgbToLinear = (c) =>
  c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);

function luminance(hex) {
  const h = hex.replace('#', '');
  const full = h.length === 3 ? [...h].map((c) => c + c).join('') : h;
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16) / 255);
  return 0.2126 * srgbToLinear(r) + 0.7152 * srgbToLinear(g) + 0.0722 * srgbToLinear(b);
}

const ratio = (a, b) => {
  const [x, y] = [luminance(a), luminance(b)].sort((m, n) => n - m);
  return (x + 0.05) / (y + 0.05);
};

/**
 * Flatten `rgb(R G B / A)` over an opaque ground. Borders are declared as an
 * alpha of the opposite ground on purpose, so their real ratio only exists
 * once composited — which is exactly why the old hand-written annotations
 * were wrong about them.
 */
function flatten(rgba, groundHex) {
  const m = rgba.match(/rgba?\(\s*(\d+)\s+(\d+)\s+(\d+)\s*\/\s*([\d.]+)\s*\)/);
  if (!m) return null;
  const [, r, g, b, a] = m;
  const alpha = parseFloat(a);
  const gh = groundHex.replace('#', '');
  const gc = [0, 2, 4].map((i) => parseInt(gh.slice(i, i + 2), 16));
  const mix = [r, g, b].map((c, i) =>
    Math.round(parseFloat(c) * alpha + gc[i] * (1 - alpha)),
  );
  return '#' + mix.map((c) => c.toString(16).padStart(2, '0')).join('');
}

/* ---- parse ---------------------------------------------------------- */

function block(css, selector) {
  const at = css.indexOf(selector);
  if (at === -1) return null;
  const open = css.indexOf('{', at);
  let depth = 0;
  for (let i = open; i < css.length; i++) {
    if (css[i] === '{') depth++;
    else if (css[i] === '}' && --depth === 0) return css.slice(open + 1, i);
  }
  return null;
}

function tokens(body) {
  const out = {};
  for (const [, name, value] of body.matchAll(
    /(--[a-z0-9-]+)\s*:\s*(#[0-9A-Fa-f]{3,8}|rgba?\([^)]*\))\s*;/g,
  )) {
    out[name] = value.trim();
  }
  return out;
}

/* ---- the contract --------------------------------------------------- */

const ALL_GROUNDS = [
  '--bg', '--surface', '--surface-hover', '--surface-2', '--surface-3',
  '--sidebar-bg', '--sidebar-hover', '--sidebar-active', '--sidebar-field',
];

// --text-subtle is the one ink that cannot clear AA on all nine grounds.
// Nine grounds do not carry four AA ink steps; the system declares the
// restriction instead of pretending otherwise.
const SUBTLE_LEGAL = [
  '--bg', '--surface', '--surface-hover', '--surface-2',
  '--sidebar-bg', '--sidebar-field',
];

const INKS = [
  { token: '--text', grounds: ALL_GROUNDS, min: AA_TEXT },
  { token: '--text-2', grounds: ALL_GROUNDS, min: AA_TEXT },
  { token: '--text-muted', grounds: ALL_GROUNDS, min: AA_TEXT },
  { token: '--text-subtle', grounds: SUBTLE_LEGAL, min: AA_TEXT },
  { token: '--ok', grounds: ALL_GROUNDS, min: AA_TEXT },
  { token: '--warn', grounds: ALL_GROUNDS, min: AA_TEXT },
  { token: '--unknown', grounds: ALL_GROUNDS, min: AA_TEXT },
  { token: '--red', grounds: ALL_GROUNDS, min: AA_TEXT },
  { token: '--accent', grounds: ALL_GROUNDS, min: AA_TEXT },
  // Non-text: must clear 3:1 per WCAG 1.4.11. Composited over its ground.
  { token: '--border-strong', grounds: ['--bg', '--surface', '--surface-2'], min: AA_UI },
];

// Label on its own fill, not on a page ground.
const PAIRS = [{ ink: '--accent-text', ground: '--accent', min: AA_TEXT }];

/* ---- run ------------------------------------------------------------ */

let css;
try {
  css = readFileSync(TOKENS, 'utf8');
} catch {
  console.error(`check-contrast: cannot read ${TOKENS}`);
  process.exit(2);
}

const themes = [
  ['light', block(css, ':root {')],
  ['dark', block(css, ':root.dark {')],
];

const failures = [];
let checks = 0;

for (const [theme, body] of themes) {
  if (!body) {
    console.error(`check-contrast: could not locate the ${theme} block`);
    process.exit(2);
  }
  const t = tokens(body);

  for (const { token, grounds, min } of INKS) {
    const raw = t[token];
    if (!raw) {
      failures.push(`${theme}  ${token} is not declared`);
      continue;
    }
    for (const g of grounds) {
      const ground = t[g];
      if (!ground) continue;
      const ink = raw.startsWith('#') ? raw : flatten(raw, ground);
      if (!ink) continue;
      const r = ratio(ink, ground);
      checks++;
      const ok = r >= min;
      if (!ok) {
        failures.push(
          `${theme}  ${token} ${ink} on ${g} ${ground}  ${r.toFixed(2)}  < ${min}`,
        );
      }
      if (VERBOSE) {
        console.log(
          `  ${ok ? 'ok  ' : 'FAIL'} ${theme.padEnd(5)} ${token.padEnd(16)} on ${g.padEnd(17)} ${r.toFixed(2)}`,
        );
      }
    }
  }

  for (const { ink, ground, min } of PAIRS) {
    if (!t[ink] || !t[ground]) continue;
    const r = ratio(t[ink], t[ground]);
    checks++;
    if (r < min) failures.push(`${theme}  ${ink} on ${ground}  ${r.toFixed(2)}  < ${min}`);
    if (VERBOSE) console.log(`  ${r >= min ? 'ok  ' : 'FAIL'} ${theme.padEnd(5)} ${ink} on ${ground} ${r.toFixed(2)}`);
  }
}

if (failures.length) {
  console.error(`\ncheck-contrast: ${failures.length} WCAG failure(s) of ${checks} checks\n`);
  for (const f of failures) console.error('  ' + f);
  console.error(
    '\nFix the token value in ui-next/src/styles/tokens.css, or declare the ground illegal\n' +
      'for that ink in scripts/check-contrast.mjs and use a darker ink at those call sites.\n',
  );
  process.exit(1);
}

console.log(`check-contrast: ${checks} ink x ground pairs clear WCAG AA in both themes.`);
