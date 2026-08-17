import { describe, expect, it } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

/**
 * Guards against unbacked trust/compliance claims reappearing on public
 * pages. Each phrase here was shipped at some point without evidence in the
 * repo (no SOC 2 report, no BAA, no SAML implementation, no public MIT
 * repo) and was pulled during the 2026-08 home page truth pass. If a claim
 * becomes true, add the evidence (a linked audit, a signed report, the
 * actual SSO code) before removing it from this list.
 */
const FORBIDDEN_PHRASES = [
  'MIT licensed',
  'MIT License',
  '100% verified',
  'no hallucinations',
  'Certified SOC 2',
  'request our latest SOC 2 report',
  'Full GDPR and HIPAA',
  'Full compliance with global privacy regulations and healthcare',
  'highest enterprise standards',
  'GDPR/HIPAA',
  'Enterprise-grade agreements',
  // The false claim was that this shipped and worked; the toggle now exists
  // honestly labeled "Coming soon", so the feature *name* is not forbidden —
  // only the specific sentence that asserted it was active and storing
  // nothing, when the state backing it was never persisted anywhere.
  'Queries and results are not stored on our servers',
  'We follow SOC 2 Type II standards for your privacy',
  // Model/preset/method counts belong in capabilities.generated.ts and must
  // be interpolated from CAPABILITIES, never hand-typed — this is the exact
  // stale figure (real count is 170 direct / 447+ routable) found in three
  // separate files (LandingPage, docs.ts, llms.txt) during the 2026-08 pass.
  '28 directly registered',
];

const SCAN_DIRS = ['src/app', 'src/components'];
const TEXT_EXTENSIONS = new Set(['.tsx', '.ts']);
const ROOT = path.join(__dirname, '..', '..');

function collectFiles(dir: string): string[] {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  return entries.flatMap((entry) => {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) return collectFiles(fullPath);
    if (TEXT_EXTENSIONS.has(path.extname(entry.name))) return [fullPath];
    return [];
  });
}

describe('public claims', () => {
  const files = SCAN_DIRS.flatMap((dir) => collectFiles(path.join(ROOT, dir))).filter(
    (file) => !file.endsWith('.test.ts') && !file.endsWith('.test.tsx'),
  );

  it.each(FORBIDDEN_PHRASES)('never reintroduces "%s"', (phrase) => {
    const offenders = files.filter((file) => fs.readFileSync(file, 'utf-8').includes(phrase));
    expect(offenders.map((file) => path.relative(ROOT, file))).toEqual([]);
  });
});
