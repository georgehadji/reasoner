/**
 * The exhibit for the home page's coding section.
 *
 * HONESTY NOTE, and the reason this file has a long comment: unlike
 * `image-showcase.ts`, this is NOT a captured run. It is the review
 * CONTRACT — the fields `coding_review_prompt` requires back on every
 * coding run (`phases/coding.py:201-215`) — filled with a small file
 * chosen so the flaws are ones `CODING_REVIEW_SYSTEM` actually names
 * (`phases/coding.py:157-167`: injection, silent error swallows, missing
 * type annotations).
 *
 * The section labels it as the shape of the output rather than as a real
 * run, and it must keep doing so. A fabricated run presented as a real one
 * would cost this page the only thing it is built on.
 *
 * CLAIM-TO-CODE, verified 2026-08-27 against the coding flow. Everything
 * this file asserts is checkable at:
 *
 * - Seven phases, in this order: `application/flows/coding.py:38-46`.
 * - Security Review is the one phase constructed with `critical=True`
 *   (`coding.py:43`), and the web path honours it — the SSE driver copies
 *   `step.critical` into `step_metadata` and makes a failure there fatal
 *   (`api/execution/pipeline.py:311,427,467). This is a phase-FAILURE gate,
 *   not a vulnerability gate: it stops a run whose review did not complete,
 *   NOT a run whose review found problems. Do not upgrade that wording.
 * - The CVE search runs before the review, is targeted at the language and
 *   framework the spec named, and its results are pasted into the review
 *   prompt (`flows/coding_phases.py:61-99`, `phases/coding.py:185-194`).
 * - Tests are told to cover the issues the review flagged
 *   (`phases/coding.py:219-225`).
 * - The eight contract clauses below are `_CODE_QUALITY_CONTRACT`
 *   (`phases/coding.py:53-64`), appended to the generation AND test prompts.
 *
 * The one thing NOT enforced in code: author ≠ reviewer lab. It is true of
 * both shipped presets — budget generates on Qwen and reviews on DeepSeek,
 * premium generates on OpenAI and reviews on Qwen
 * (`domain/preset_registry.py:728-761,766-772`) — but `BlocDiversityConstraint`
 * covers perspective and debate roles only; `_GENERATOR_ROLES` does not
 * include `coding_generate` (`infrastructure/llm/constraints/bloc_diversity.py:22-27`).
 * So the section says the presets route it that way. It must never say "by
 * rule" or "enforced", which is the masthead's specific promise about
 * epistemic labels and would be a lie here.
 *
 * Model ids are deliberately absent, for the same reason the image showcase
 * hides them: naming them dates the page the moment a tier is re-ranked and
 * turns a claim about how a run is composed into a spec sheet.
 */

/** The request, as a user would type it. */
export const CODE_SHOWCASE_REQUEST = 'A SQLite-backed user store with lookup by id';

export interface CodeLine {
  /** Rendered in the gutter. */
  readonly n: number;
  readonly text: string;
  /** Marked in the gutter because a finding below cites it. */
  readonly flagged?: boolean;
}

/**
 * The file as the generating model returned it, flaws intact.
 *
 * Kept under ~45 columns on purpose. The plate this renders in scrolls
 * horizontally if a line overruns it, and a scrollbar through the middle of
 * the page's exhibit reads as something unfinished rather than as something
 * to look at. The query is bound to a local first for the same reason —
 * shorter line, and it is how a model tends to write it anyway.
 */
export const CODE_SHOWCASE_FILE = {
  path: 'store/users.py',
  lines: [
    { n: 1, text: 'def get_user(conn, uid):', flagged: true },
    { n: 2, text: '    cur = conn.cursor()' },
    { n: 3, text: '    q = f"SELECT * FROM users WHERE id={uid}"', flagged: true },
    { n: 4, text: '    cur.execute(q)' },
    { n: 5, text: '    try:' },
    { n: 6, text: '        return cur.fetchone()' },
    { n: 7, text: '    except Exception:', flagged: true },
    { n: 8, text: '        return None' },
  ] satisfies readonly CodeLine[],
} as const;

export interface ReviewFinding {
  /** The review returns these in three separate arrays, hence three tiers. */
  readonly severity: 'CRITICAL' | 'HIGH' | 'MEDIUM';
  readonly line: number;
  readonly issue: string;
  /** `medium_issues` is the one tier whose schema carries no `fix` field. */
  readonly fix?: string;
}

export const CODE_SHOWCASE_FINDINGS: readonly ReviewFinding[] = [
  {
    severity: 'CRITICAL',
    line: 3,
    issue: 'uid is interpolated straight into the statement. A crafted id runs SQL of its own.',
    fix: 'Bind it: execute("… WHERE id = ?", (uid,)).',
  },
  {
    severity: 'HIGH',
    line: 7,
    issue:
      'A bare except returns None, so a dead connection and a missing user are the same answer.',
    fix: 'Catch sqlite3.Error, log it, re-raise.',
  },
  {
    severity: 'MEDIUM',
    line: 1,
    issue: 'No type annotations on the signature.',
  },
] as const;

/** One of the two values `overall_verdict` is allowed to take. */
export const CODE_SHOWCASE_VERDICT = 'NEEDS_FIXES';

/**
 * `_CODE_QUALITY_CONTRACT`, condensed to display length. Eight clauses,
 * appended to every generation prompt and every test prompt — this is the
 * standard the code is written to before anyone reviews it.
 */
export const CODE_CONTRACT: readonly string[] = [
  'Type annotations on every signature',
  'Specific exception types, never a bare except',
  'Input validation at every public boundary',
  'No hardcoded secrets, credentials or magic numbers',
  'Structured logging, zero print statements',
  'Complete implementation: no TODO stubs, no pass',
  'Thread and async safety where the interface implies it',
  'Comments only where the why is non-obvious',
] as const;
