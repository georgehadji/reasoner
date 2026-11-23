/**
 * Sector pages (/for/[slug]) and the landing page's sector index.
 *
 * Each sector leads with the one question its reviewer has to answer before a
 * pilot can start (spec/conversion-research.md §2.2), then a review sheet:
 * the questions that reviewer will ask, each with a status. Every
 * `available` answer is backed by code or a repo document; anything not
 * verified is `to-confirm` with an [INPUT REQUIRED] note, never a guess.
 */

import type { MethodId } from './types';

export type ReviewStatus = 'available' | 'not-available' | 'to-confirm';

/** A method as the page names it; `hint` keys its description in
 *  lib/method-hints.tsx where one exists. */
export interface SectorMethod {
  name: string;
  hint?: MethodId;
}

export interface ReviewItem {
  question: string;
  status: ReviewStatus;
  answer: string;
  href?: string;
}

export interface Sector {
  slug: string;
  name: string;
  /** The reviewer's gating question, the page's lead sentence. */
  gate: string;
  use: string;
  /** Real `method` values in preset_registry.py. */
  methods: readonly SectorMethod[];
  /** Run on Western-only routing (US and EU labs only). */
  westernOnly?: boolean;
  /** The line it does not cross, stated up front. */
  limit: string;
  review: ReviewItem[];
}

export const REVIEW_STATUS_LABEL: Record<ReviewStatus, string> = {
  available: 'Available',
  'not-available': 'Not available',
  'to-confirm': 'To confirm',
};

/* ── Shared answers ────────────────────────────────────────────────
   One source per fact, so a correction lands on every sector page. */

const SUBPROCESSORS: ReviewItem = {
  question: 'Which companies can see our data?',
  status: 'available',
  answer:
    'Every model provider a request can reach, plus OpenRouter, which routes to them. The list is generated from the routing registry, so it cannot drift from what runs.',
  href: '/subprocessors',
};

const WESTERN_ONLY: ReviewItem = {
  question: 'Can we keep requests away from non-Western model labs?',
  status: 'available',
  answer:
    'Yes. Every preset has a Western-only twin that uses US and EU labs only, and the provider builder refuses any model from another bloc while it is on.',
  href: '/#labs',
};

const SELF_HOST: ReviewItem = {
  question: 'Can it run in our own infrastructure?',
  status: 'available',
  answer:
    'Yes. The code is source-available (Business Source License 1.1, which permits self-hosting) and the full stack runs from one Docker Compose file. Model calls still go to the providers you configure.',
  href: '/security',
};

const AIR_GAP: ReviewItem = {
  question: 'Can it run with no outside connection?',
  status: 'to-confirm',
  answer:
    'Local models run through Ollama, but there is no documented setup that works with no connection to OpenRouter.',
};

const TRAINING: ReviewItem = {
  question: 'Is our data used to train models?',
  status: 'to-confirm',
  answer:
    'Not by us. Each model provider has its own terms. [INPUT REQUIRED: which providers may retain or train on API traffic, and is a no-training setting enforced?]',
  href: '/security',
};

const RETENTION: ReviewItem = {
  question: 'Can we run with nothing stored?',
  status: 'not-available',
  answer:
    'Not yet. Runs are stored so you can return to them. You can erase them at any time, or delete the account from settings.',
  href: '/privacy',
};

const ENCRYPTION: ReviewItem = {
  question: 'How is data protected?',
  status: 'available',
  answer:
    'Field-level encryption at rest, and HTTPS with HSTS in transit. This is not end-to-end: the model provider decrypts a request to answer it.',
  href: '/security',
};

const RUN_RECORD: ReviewItem = {
  question: 'Can we show how an answer was reached?',
  status: 'available',
  answer:
    'Each run is stored as a log of events: every phase, which model wrote it, what the critic scored, and a verified, hypothesis or unknown label on each claim.',
  href: '/how-it-works',
};

const RESIDENCY: ReviewItem = {
  question: 'Where is data stored and processed?',
  status: 'to-confirm',
  answer: '[INPUT REQUIRED: which regions data is stored and processed in]',
};

const SOC2: ReviewItem = {
  question: 'Is there a SOC 2 or ISO 27001 report?',
  status: 'not-available',
  answer: 'Not yet certified.',
  href: '/security',
};

const DATA_AGREEMENTS: ReviewItem = {
  question: 'Is there a data-processing agreement, or a BAA for health data?',
  status: 'to-confirm',
  answer:
    '[INPUT REQUIRED: is there a GDPR data-processing agreement, or a HIPAA BAA, covering OpenRouter and every model provider?]',
};

export const SECTORS: readonly Sector[] = [
  {
    slug: 'defence',
    name: 'Defence and security',
    gate: 'Can it run where our information is allowed to go?',
    use: 'Structured adversarial analysis of plans: red-team a course of action, or run a pre-mortem on why it failed.',
    methods: [{ name: 'Debate', hint: 'debate' }, { name: 'Pre-Mortem', hint: 'pre-mortem' }, { name: 'Dialectical', hint: 'dialectical' }],
    westernOnly: true,
    limit: 'Analysis for the people who decide. It does not decide.',
    review: [SELF_HOST, AIR_GAP, WESTERN_ONLY, SUBPROCESSORS, RESIDENCY, SOC2],
  },
  {
    slug: 'healthcare',
    name: 'Healthcare operations',
    gate: 'Will it pass our information-governance review?',
    use: 'Staffing, procurement and incident root-cause analysis. Morbidity and mortality reviews as pre-mortem or Socratic questioning. Comparing guidelines with cited sources.',
    methods: [{ name: 'Pre-Mortem', hint: 'pre-mortem' }, { name: 'Socratic', hint: 'socratic' }, { name: 'Research', hint: 'research' }],
    limit: 'Not for diagnosis or treatment decisions. Do not enter patient data.',
    review: [
      DATA_AGREEMENTS,
      {
        question: 'Has it been assessed against the NHS DTAC?',
        status: 'to-confirm',
        answer: '[INPUT REQUIRED: has a DTAC submission been prepared, and is a clinical safety case in scope?]',
      },
      TRAINING,
      RETENTION,
      ENCRYPTION,
      SUBPROCESSORS,
    ],
  },
  {
    slug: 'research',
    name: 'Research and teaching',
    gate: 'Will our IT security review approve it for research data?',
    use: 'Research design and peer-review support: generate hypotheses and try to disprove them, update beliefs on evidence, teach critical thinking by questioning.',
    methods: [
      { name: 'Scientific', hint: 'scientific' },
      { name: 'Bayesian', hint: 'bayesian' },
      { name: 'Socratic', hint: 'socratic' },
      { name: 'Research', hint: 'research' },
    ],
    limit: 'A reviewer’s second reader, not a replacement for one.',
    review: [TRAINING, RETENTION, SUBPROCESSORS, ENCRYPTION, SELF_HOST, RUN_RECORD],
  },
  {
    slug: 'legal',
    name: 'Legal and compliance',
    gate: 'Can we keep client confidences while we use it?',
    use: 'Stress-test an argument against opposing counsel’s likely positions, run a pre-mortem on contract risk, and look for gaps against a regulation.',
    methods: [{ name: 'Debate', hint: 'debate' }, { name: 'Jury', hint: 'jury' }, { name: 'Pre-Mortem', hint: 'pre-mortem' }],
    limit: 'Not legal advice. Check every citation before it leaves the firm.',
    review: [TRAINING, RETENTION, SUBPROCESSORS, ENCRYPTION, SELF_HOST, RUN_RECORD],
  },
  {
    slug: 'engineering',
    name: 'Aerospace and engineering',
    gate: 'Can controlled technical data stay under our control?',
    use: 'Design reviews, failure-mode analysis in the style of an FMEA, and critique of requirements before they are frozen.',
    methods: [{ name: 'Pre-Mortem', hint: 'pre-mortem' }, { name: 'Iterative Critique' }],
    limit:
      'Does not replace certified safety analysis. Do not enter export-controlled (ITAR or EAR) technical data into the hosted service.',
    review: [SELF_HOST, AIR_GAP, WESTERN_ONLY, SUBPROCESSORS, RESIDENCY],
  },
  {
    slug: 'public-sector',
    name: 'Government and policy',
    gate: 'Can we explain in public how an output was reached?',
    use: 'Policy options analysis, structured expert consensus, and stress-testing scenarios before they are published.',
    methods: [{ name: 'Delphi', hint: 'delphi' }, { name: 'Dialectical', hint: 'dialectical' }],
    limit: 'Options and their weaknesses, not a recommendation to adopt.',
    review: [RUN_RECORD, WESTERN_ONLY, SUBPROCESSORS, RESIDENCY, SOC2, RETENTION],
  },
];

export function getSector(slug: string): Sector | undefined {
  return SECTORS.find((s) => s.slug === slug);
}
