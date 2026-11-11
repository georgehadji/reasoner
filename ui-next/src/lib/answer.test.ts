import { describe, expect, it } from 'vitest';
import {
  answerMarkdown,
  extractHeadings,
  findAnswer,
  slugify,
  summarizePhase,
  summarizeRun,
  type PhaseLike,
} from './answer';

const phase = (index: number, num: number, name: string, data: unknown): PhaseLike => ({
  index,
  phase: num,
  name,
  data,
});

const orchestrated: PhaseLike[] = [
  phase(0, 0, 'Classification', { task_type: 'strategy', language: 'English', models: ['openai/gpt-5-mini'] }),
  phase(1, 1, 'Decomposition', { sub_problems: [{}, {}, {}], assumptions: [{}, {}], models: ['anthropic/claude-haiku'] }),
  phase(2, 2, 'Perspectives', {
    candidates: [
      { perspective: 'constructive', model_used: 'openai/gpt-5' },
      { perspective: 'destructive', model_used: 'google/gemini-3-pro' },
      { perspective: 'systemic', model_used: 'x-ai/grok-4' },
      { perspective: 'minimalist', model_used: 'openai/gpt-5' },
    ],
  }),
  // Shape of `_ser_3`'s scores: the composite is `total`.
  phase(3, 3, 'Critique & Pruning', { scores: [{ perspective: 'a', total: 6.5 }, { perspective: 'b', total: 8.25 }, { perspective: 'c', total: 7 }] }),
  phase(4, 5, 'Synthesis', {
    core_solution: 'Ship the small version first.',
    critical_insights: ['Scope is the risk'],
    action_blueprint: [{ step: 'Week 1', action: 'Cut scope' }],
    open_questions: ['Who owns QA?'],
    sources: [{ title: 'A', url: 'https://a.example' }, { title: 'B', url: 'https://b.example' }],
    models: ['anthropic/claude-sonnet'],
  }),
];

describe('findAnswer', () => {
  it('picks the synthesis phase and leaves the rest as process', () => {
    const found = findAnswer(orchestrated);
    expect(found?.kind).toBe('synthesis');
    expect(found?.answer.name).toBe('Synthesis');
    expect(found?.process.map((p) => p.name)).toEqual([
      'Classification',
      'Decomposition',
      'Perspectives',
      'Critique & Pruning',
    ]);
  });

  it('picks the phase that carries the final article', () => {
    const phases = [
      phase(0, 0, 'Classification', { task_type: 'writing' }),
      phase(1, 2, 'Outline', { writing_state: { outline: [{}, {}] } }),
      phase(2, 4, 'Final Polish', { writing_state: { final_article: '# Burnout\n\nBody.' } }),
      phase(3, 5, 'Fact Check Report', { writing_state: { factcheck_reviews: [{}] } }),
    ];
    const found = findAnswer(phases);
    expect(found?.kind).toBe('article');
    expect(found?.answer.name).toBe('Final Polish');
    expect(found?.process).toHaveLength(3);
  });

  it('takes the last answer when a run has more than one', () => {
    const phases = [
      ...orchestrated,
      phase(5, 5, 'Final Verdict', { core_solution: 'Later answer.' }),
    ];
    expect(findAnswer(phases)?.answer.name).toBe('Final Verdict');
  });

  it('returns null when nothing is an answer, or the answer is the only phase', () => {
    expect(findAnswer(orchestrated.slice(0, 3))).toBeNull();
    expect(findAnswer([orchestrated[4]])).toBeNull();
    expect(findAnswer([])).toBeNull();
  });

  it("finds each method's own final answer, not only core_solution", () => {
    const cove = [
      phase(0, 2, 'Draft', { cove_state: { draft_answer: 'draft' } }),
      phase(1, 5, 'Final Revision', { cove_state: { revised_answer: 'Revised.' } }),
    ];
    expect(findAnswer(cove)?.answer.name).toBe('Final Revision');
    const preMortem = [
      phase(0, 2, 'Failure Narrative', { pre_mortem_state: { failure_narrative: 'x' } }),
      phase(1, 5, 'Hardened Redesign', { pre_mortem_state: { hardened_solution: 'Harden it.' } }),
      phase(2, 6, 'Egress Rewrite', { rewritten: true }),
    ];
    expect(findAnswer(preMortem)?.answer.name).toBe('Hardened Redesign');
  });

  it('prefers the humanized article, which supersedes the assembled one', () => {
    const phases = [
      phase(0, 5, 'Final Assembly', { writing_state: { final_article: 'Assembled.' } }),
      phase(1, 6, 'Humanize', { writing_state: { humanized_article: 'Humanized.' } }),
      phase(2, 7, 'Fact Check Report', { writing_state: { factcheck_reviews: [{}], sources_cited: [] } }),
    ];
    const found = findAnswer(phases);
    expect(found?.kind).toBe('article');
    expect(found?.answer.name).toBe('Humanize');
    expect(answerMarkdown(found!)).toBe('Humanized.\n');
  });

  it('keeps pipeline order when the synthesis payload carries no answer', () => {
    // A debate run whose Synthesis payload held only tokens and models: picking
    // it would put an empty card on top.
    const phases = [
      phase(0, 2, 'Opening Statements', { debate_rounds: [{}] }),
      phase(1, 5, 'Synthesis', { tokens: { input: 1, output: 2 }, models: ['m'] }),
      phase(2, 5.5, 'Egress Rewrite', { rewritten: true, strategy: 'paraphrase' }),
    ];
    expect(findAnswer(phases)).toBeNull();
  });

  it('does not treat an empty article as the answer', () => {
    const phases = [
      phase(0, 0, 'Classification', {}),
      phase(1, 4, 'Final Polish', { writing_state: { final_article: '   ' } }),
    ];
    expect(findAnswer(phases)).toBeNull();
  });
});

describe('summarizePhase', () => {
  it('says what each common phase found, from data already in the payload', () => {
    expect(summarizePhase(orchestrated[0])).toBe('strategy · English');
    expect(summarizePhase(orchestrated[1])).toBe('3 sub-problems · 2 assumptions');
    expect(summarizePhase(orchestrated[2])).toBe('4 perspectives from 3 models');
    expect(summarizePhase(orchestrated[3])).toBe('3 scored, top 8.3/10');
  });

  it('counts vetted sources and article steps', () => {
    expect(summarizePhase(phase(0, 1, 'Context Vetting', { vetted_context: [{}, {}] }))).toBe('2 sources vetted');
    expect(summarizePhase(phase(0, 2, 'Outline', { writing_state: { outline: [{}, {}, {}] } }))).toBe('3 outline sections');
    expect(
      summarizePhase(phase(0, 4, 'Final Polish', { writing_state: { final_article: 'one two three four' } })),
    ).toBe('4 words');
  });

  it('falls back to counting the lists inside a method state', () => {
    expect(
      summarizePhase(phase(0, 2, 'Hypotheses', { scientific_state: { hypotheses: [{}, {}, {}] } })),
    ).toBe('3 hypotheses');
    expect(
      summarizePhase(phase(0, 3, 'Tests', { scientific_state: { test_results: [{}] } })),
    ).toBe('1 test result');
  });

  it('returns null when there is nothing countable', () => {
    expect(summarizePhase(phase(0, 2, 'Odd', { note: 'text' }))).toBeNull();
    expect(summarizePhase(phase(0, 2, 'Odd', null))).toBeNull();
  });
});

describe('summarizeRun', () => {
  it('counts phases, distinct models and sources', () => {
    expect(summarizeRun(orchestrated)).toBe('5 phases · 6 models · 2 sources');
  });

  it('adds duration and cost when known', () => {
    expect(summarizeRun(orchestrated.slice(0, 1), { duration: 161, cost: 0.0612 })).toBe(
      '1 phase · 1 model · 2m 41s · $0.06',
    );
  });
});

describe('answerMarkdown', () => {
  it('gives the synthesis without the per-phase heading', () => {
    const md = answerMarkdown(findAnswer(orchestrated)!);
    expect(md).toContain('Ship the small version first.');
    expect(md).toContain('Week 1');
    expect(md).not.toMatch(/Phase \d/);
    expect(md).not.toContain('Models:');
  });

  it('gives the article and its sources, not the drafting log', () => {
    const found = findAnswer([
      phase(0, 0, 'Classification', {}),
      phase(1, 4, 'Final Polish', {
        writing_state: {
          final_article: '# Burnout\n\nBody.',
          outline: [{ heading: 'Draft outline' }],
          sources_cited: [{ title: 'WHO', url: 'https://who.int' }, 'Plain source'],
        },
      }),
    ])!;
    const md = answerMarkdown(found);
    expect(md.startsWith('# Burnout')).toBe(true);
    expect(md).toContain('[WHO](https://who.int)');
    expect(md).toContain('- Plain source');
    expect(md).not.toContain('Draft outline');
  });
});

describe('headings', () => {
  it('slugifies the way rendered headings are anchored', () => {
    expect(slugify('Why it Matters: 2026!')).toBe('why-it-matters-2026');
  });

  it('lists h2 and h3 headings outside code fences', () => {
    const md = '# Title\n\n## First part\ntext\n```\n## not a heading\n```\n### Detail\n## Second part';
    expect(extractHeadings(md)).toEqual([
      { level: 2, text: 'First part', id: 'first-part' },
      { level: 3, text: 'Detail', id: 'detail' },
      { level: 2, text: 'Second part', id: 'second-part' },
    ]);
  });
});
