/**
 * The landing page's factual content: ONE real Reasoner run, parsed into the
 * record structure the page renders.
 *
 * The run was captured 2026-08-17 by calling the production SSE pipeline
 * in-process — the same code path a live request hits — and saved verbatim to
 * `demo-run.json`. Nothing here is written by hand: every number, source URL,
 * score, survival rate, and sentence on the home page comes out of this file.
 * Regenerate by capturing a fresh run, never by editing the JSON.
 *
 * Why a local parser instead of `lib/markdown.ts`: the home page renders the
 * synthesis TWICE — once stripped of its citations and epistemic labels, once
 * with them — because that difference is the product's entire argument. A
 * general markdown renderer emits one tree with the apparatus baked in and
 * cannot answer "what would this paragraph look like without the record". The
 * block/segment split below exists for exactly that, and stops at the four
 * inline forms this run actually contains.
 */
import demoRunJson from '@/lib/demo-run.json';

/* ── Raw event shapes (only the fields this module reads) ─────────── */

interface RawScore {
  perspective: string;
  logical_consistency: number;
  evidence_support: number;
  failure_resilience: number;
  feasibility: number;
  total: number;
  bias_flags: string[];
  steel_man: string;
  is_top: boolean;
}

interface RawCandidate {
  perspective: string;
  content: string;
  key_insights: string[];
}

interface RawSource {
  title: string;
  url: string;
}

interface RawEvent {
  type: string;
  name?: string;
  preset?: string;
  text?: string;
  total_tokens?: { input: number; output: number; total: number };
  total_cost_usd?: number;
  duration?: number;
  data?: {
    duration?: number;
    models?: string[];
    tokens?: { input: number; output: number };
    scores?: RawScore[];
    candidates?: RawCandidate[];
    web_discovery_results?: RawSource[];
    tests?: Array<{ scenario: string; survival_rate: number; failure_mode: string }>;
  };
}

const EVENTS = demoRunJson as RawEvent[];

function phaseData(name: string) {
  return EVENTS.find((e) => e.type === 'phase_complete' && e.name === name)?.data;
}

/* ── Public record types ──────────────────────────────────────────── */

export interface RunPhase {
  /** Anchor id — also the section's href target. */
  id: string;
  /** The pipeline's own phase name. The page's section names are these. */
  name: string;
  seconds: number;
  models: string[];
}

export interface RunSource {
  index: number;
  title: string;
  url: string;
  domain: string;
}

export interface RunPosition {
  /** The perspective role the pipeline assigns: constructive, destructive, … */
  id: string;
  insights: string[];
  /** Opening of the position, cut at a sentence boundary. Parsed, because
   *  generated positions carry inline epistemic labels of their own — the
   *  labelling starts in phase 2, not at synthesis. */
  excerpt: Segment[];
}

export interface RunScore {
  position: string;
  logicalConsistency: number;
  evidenceSupport: number;
  failureResilience: number;
  feasibility: number;
  /** Post-penalty score, NOT the mean of the four axes above. */
  total: number;
  biasFlags: string[];
  steelMan: string;
  retained: boolean;
}

export interface RunStressTest {
  scenario: string;
  survivalRate: number;
  /** Empty string when the run returned no prose for this test. */
  failureMode: string;
}

/* ── Synthesis: blocks of segments ────────────────────────────────── */

export type EpistemicLabel = 'VERIFIED' | 'HYPOTHESIS' | 'UNKNOWN';

export type Segment =
  | { kind: 'text'; text: string }
  | { kind: 'strong'; text: string }
  /** Apparatus. Dropped entirely in the page's "answer only" rendering. */
  | { kind: 'label'; label: EpistemicLabel; qualifier: string }
  | { kind: 'cite'; index: number; url: string; domain: string };

export type Block =
  | { kind: 'heading'; text: string }
  | { kind: 'subheading'; text: string }
  | { kind: 'para'; segments: Segment[] }
  | { kind: 'item'; ordinal: string | null; segments: Segment[] };

/** `**bold**`, `[source](url)`, and `[LABEL optional qualifier]` — in one pass,
 *  so a citation inside a bolded run cannot be double-matched. */
const INLINE = /\*\*(.+?)\*\*|\[source\]\((https?:\/\/[^)]+)\)|\[(VERIFIED|HYPOTHESIS|UNKNOWN)([^\]]*)\]/g;

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

/** Citations are numbered in order of first appearance across the whole
 *  synthesis, so the same URL cited twice keeps one number — the convention
 *  every reference list already uses. */
function makeCiteNumbering() {
  const seen = new Map<string, number>();
  return {
    number(url: string): number {
      const existing = seen.get(url);
      if (existing !== undefined) return existing;
      const next = seen.size + 1;
      seen.set(url, next);
      return next;
    },
    list(): RunSource[] {
      return [...seen.entries()].map(([url, index]) => ({
        index,
        url,
        domain: hostOf(url),
        title: hostOf(url),
      }));
    },
  };
}

function parseInline(line: string, cites: ReturnType<typeof makeCiteNumbering>): Segment[] {
  const segments: Segment[] = [];
  let cursor = 0;
  let match: RegExpExecArray | null;
  INLINE.lastIndex = 0;

  const pushText = (text: string) => {
    if (text) segments.push({ kind: 'text', text });
  };

  while ((match = INLINE.exec(line))) {
    pushText(line.slice(cursor, match.index));
    const [, bold, citeUrl, label, qualifier] = match;
    if (bold) {
      segments.push({ kind: 'strong', text: bold });
    } else if (citeUrl) {
      segments.push({
        kind: 'cite',
        index: cites.number(citeUrl),
        url: citeUrl,
        domain: hostOf(citeUrl),
      });
    } else if (label) {
      segments.push({
        kind: 'label',
        label: label as EpistemicLabel,
        qualifier: qualifier.trim(),
      });
    }
    cursor = match.index + match[0].length;
  }

  pushText(line.slice(cursor));
  return segments;
}

/** Chunks arrive off the SSE stream a sentence at a time with no trailing
 *  space and no trailing newline, so the block structure has to be put back.
 *  A chunk that opens with a markdown marker started a new line in the model's
 *  output; anything else continued the sentence before it. Joining everything
 *  with a space instead swallows every list item into the paragraph above it. */
const BLOCK_START = /^(#{3,4} |- |\d+\.)/;

const SYNTHESIS_TEXT = EVENTS.filter((e) => e.type === 'text_chunk')
  .map((e) => e.text ?? '')
  .reduce((text, chunk, i) => {
    if (i === 0) return chunk;
    return text + (BLOCK_START.test(chunk) ? '\n' : ' ') + chunk;
  }, '');

function parseSynthesis(): { blocks: Block[]; citations: RunSource[] } {
  const cites = makeCiteNumbering();
  const blocks: Block[] = [];

  for (const rawLine of SYNTHESIS_TEXT.split('\n')) {
    const line = rawLine.trim();
    if (!line) continue;

    if (line.startsWith('#### ')) {
      blocks.push({ kind: 'subheading', text: line.slice(5) });
    } else if (line.startsWith('### ')) {
      blocks.push({ kind: 'heading', text: line.slice(4) });
    } else if (line.startsWith('- ')) {
      blocks.push({ kind: 'item', ordinal: null, segments: parseInline(line.slice(2), cites) });
    } else {
      const numbered = /^(\d+)\.\s*(.*)$/.exec(line);
      if (numbered) {
        blocks.push({
          kind: 'item',
          ordinal: numbered[1],
          segments: parseInline(numbered[2], cites),
        });
      } else {
        blocks.push({ kind: 'para', segments: parseInline(line, cites) });
      }
    }
  }

  return { blocks, citations: cites.list() };
}

/** First whole sentences of a position, up to a readable column. Cutting at a
 *  sentence boundary rather than a character count keeps the excerpt something
 *  the model actually said, and the ellipsis marks that there is more. */
function excerptOf(content: string, budget = 260): string {
  if (content.length <= budget) return content;
  const window = content.slice(0, budget);
  const lastStop = Math.max(window.lastIndexOf('. '), window.lastIndexOf('.\n'));
  let cut = lastStop > 0 ? window.slice(0, lastStop + 1) : window.trimEnd();

  /* Never end inside a `[LABEL …]`. A half-bracket does not match the inline
     pattern, so it survives to the page as the literal text "[VERIFIED". */
  const opened = cut.lastIndexOf('[');
  if (opened > cut.lastIndexOf(']')) cut = cut.slice(0, opened).trimEnd();

  return `${cut} …`;
}

/* ── The record ───────────────────────────────────────────────────── */

const PHASE_NAMES = [
  ['evidence', 'Evidence Search'],
  ['positions', 'Perspectives'],
  ['adjudication', 'Critique & Pruning'],
  ['stress', 'Stress Testing'],
  ['synthesis', 'Synthesis'],
] as const;

const done = EVENTS.find((e) => e.type === 'done');
const synthesis = parseSynthesis();

export const RUN = {
  question: 'Should a 12-person startup switch from a monorepo to polyrepo as it scales?',
  preset: EVENTS.find((e) => e.type === 'start' && e.preset)?.preset ?? '',
  capturedOn: '2026-08-17',

  phases: PHASE_NAMES.map(([id, name]): RunPhase => {
    const d = phaseData(name);
    return { id, name, seconds: d?.duration ?? 0, models: d?.models ?? [] };
  }),

  sources: (phaseData('Evidence Search')?.web_discovery_results ?? []).map(
    (s, i): RunSource => ({
      index: i + 1,
      title: s.title,
      url: s.url,
      domain: hostOf(s.url),
    }),
  ),

  positions: (phaseData('Perspectives')?.candidates ?? []).map(
    (c): RunPosition => ({
      id: c.perspective,
      insights: c.key_insights ?? [],
      excerpt: parseInline(excerptOf(c.content), makeCiteNumbering()),
    }),
  ),

  scores: (phaseData('Critique & Pruning')?.scores ?? []).map(
    (s): RunScore => ({
      position: s.perspective,
      logicalConsistency: s.logical_consistency,
      evidenceSupport: s.evidence_support,
      failureResilience: s.failure_resilience,
      feasibility: s.feasibility,
      total: s.total,
      biasFlags: s.bias_flags ?? [],
      steelMan: s.steel_man,
      retained: s.is_top,
    }),
  ),

  stress: (phaseData('Stress Testing')?.tests ?? []).map(
    (t): RunStressTest => ({
      scenario: t.scenario,
      survivalRate: t.survival_rate,
      failureMode: t.failure_mode ?? '',
    }),
  ),

  synthesis: synthesis.blocks,
  citations: synthesis.citations,

  ledger: {
    seconds: done?.duration ?? 0,
    tokensIn: done?.total_tokens?.input ?? 0,
    tokensOut: done?.total_tokens?.output ?? 0,
    tokensTotal: done?.total_tokens?.total ?? 0,
    costUsd: done?.total_cost_usd ?? 0,
  },
} as const;

/** The four axes the critique phase scores every position on, in the order the
 *  matrix presents them. Row order is fixed here so the header and body of the
 *  table can never disagree. */
export const SCORE_AXES = [
  { key: 'logicalConsistency', label: 'Logical consistency' },
  { key: 'evidenceSupport', label: 'Evidence support' },
  { key: 'failureResilience', label: 'Failure resilience' },
  { key: 'feasibility', label: 'Feasibility' },
] as const satisfies ReadonlyArray<{ key: keyof RunScore; label: string }>;

/** Distinct models this run actually touched, in phase order. */
export const RUN_MODELS: string[] = [
  ...new Set(RUN.phases.flatMap((p) => p.models)),
];
