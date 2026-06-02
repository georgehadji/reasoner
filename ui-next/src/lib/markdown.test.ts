/**
 * Edge-case tests for markdown.ts — buildMarkdownFromPhase / buildMarkdownFromPhases.
 *
 * Covers: all phase data formats, null/malformed data, XSS vectors,
 * nested state objects (cove_state, bayesian_state, etc.), empty phases.
 */

import { describe, it, expect } from 'vitest';
import { buildMarkdownFromPhase, buildMarkdownFromPhases } from './markdown';


describe('buildMarkdownFromPhase — edge cases', () => {
  it('handles null data', () => {
    const md = buildMarkdownFromPhase(0, 1, 'Test', null);
    expect(md).toContain('Phase 1');
    expect(md).toContain('Test');
    expect(md).toContain('null');
  });

  it('handles undefined data', () => {
    const md = buildMarkdownFromPhase(0, 1, 'Test', undefined);
    expect(md).toContain('undefined');
  });

  it('handles non-object data (string)', () => {
    const md = buildMarkdownFromPhase(0, 1, 'Test', 'simple text');
    expect(md).toContain('simple text');
  });

  it('handles non-object data (number)', () => {
    const md = buildMarkdownFromPhase(0, 1, 'Test', 42);
    expect(md).toContain('42');
  });

  it('handles empty object data', () => {
    const md = buildMarkdownFromPhase(0, 1, 'Empty', {});
    expect(md).toContain('No content');
  });

  it('renders solution field', () => {
    const md = buildMarkdownFromPhase(0, 5, 'Synthesis', {
      solution: 'The answer is 42.',
    });
    expect(md).toContain('The answer is 42');
  });

  it('renders models metadata', () => {
    const md = buildMarkdownFromPhase(0, 2, 'Perspectives', {
      models: ['openai/gpt-4o', 'anthropic/claude-sonnet'],
    });
    expect(md).toContain('gpt-4o');
    expect(md).toContain('claude-sonnet');
    expect(md).toContain('Models:');
  });

  it('renders subagents metadata', () => {
    const md = buildMarkdownFromPhase(0, 2, 'Perspectives', {
      subagents: [
        { name: 'Analyst', model: 'openai/gpt-4o-mini' },
        { name: 'Critic', model: 'anthropic/claude-haiku' },
      ],
    });
    expect(md).toContain('Analyst');
    expect(md).toContain('Critic');
    expect(md).toContain('gpt-4o-mini');
  });

  it('renders classification fields', () => {
    const md = buildMarkdownFromPhase(0, 0, 'Classification', {
      task_type: 'analysis',
      rationale: 'This requires multi-perspective reasoning.',
      language: 'en',
    });
    expect(md).toContain('Task Type:');
    expect(md).toContain('analysis');
    expect(md).toContain('Language:');
  });

  it('renders decomposition fields', () => {
    const md = buildMarkdownFromPhase(0, 1, 'Decomposition', {
      sub_problems: [
        { description: 'Problem A', constraints: ['time', 'budget'] },
        { description: 'Problem B', constraints: [] },
      ],
      assumptions: [
        { label: 'A1', text: 'Market is stable', rationale: 'Historical data' },
      ],
    });
    expect(md).toContain('Sub-Problems');
    expect(md).toContain('Problem A');
    expect(md).toContain('time, budget');
    expect(md).toContain('Assumptions');
    expect(md).toContain('A1');
  });

  it('renders perspectives with candidates', () => {
    const md = buildMarkdownFromPhase(0, 2, 'Perspectives', {
      candidates: [
        {
          perspective: 'Constructive',
          model_used: 'openai/gpt-4o',
          content: 'This is a constructive analysis.',
          key_insights: ['Insight 1', 'Insight 2'],
        },
      ],
    });
    expect(md).toContain('Constructive');
    expect(md).toContain('gpt-4o');
    expect(md).toContain('constructive analysis');
    expect(md).toContain('Insight 1');
  });

  it('renders critique scores matrix', () => {
    const md = buildMarkdownFromPhase(0, 3, 'Critique', {
      critic_scores: [
        {
          critic_id: 'logic-check',
          critic_model: 'openai/gpt-4o',
          candidate_scores: {
            gen1: { total: 8.5, steel_man: 'Well reasoned.' },
          },
          dissenting_note: 'Minor logical flaw.',
        },
      ],
    });
    expect(md).toContain('logic-check');
    expect(md).toContain('gpt-4o');
    expect(md).toContain('8.5');
    expect(md).toContain('Well reasoned');
    expect(md).toContain('Dissenting');
  });

  it('renders stress tests', () => {
    const md = buildMarkdownFromPhase(0, 4, 'Stress Testing', {
      tests: [
        {
          scenario: 'Market crash',
          survival_rate: 0.75,
          failure_mode: 'Cash flow issue',
          recovery_path: 'Emergency funding',
        },
      ],
    });
    expect(md).toContain('Market crash');
    expect(md).toContain('75%');
    expect(md).toContain('Cash flow issue');
  });

  it('renders synthesis with critical_insights and action_blueprint', () => {
    const md = buildMarkdownFromPhase(0, 5, 'Synthesis', {
      core_solution: 'The optimal strategy is diversification.',
      critical_insights: ['Diversification reduces risk', 'Long-term focus wins'],
      action_blueprint: ['Step 1: Assess', 'Step 2: Allocate'],
      open_questions: ['What about inflation?'],
      sources: [{ title: 'Research Paper', url: 'https://example.com' }],
    });
    expect(md).toContain('diversification');
    expect(md).toContain('Critical Insights');
    expect(md).toContain('Step 1');
    expect(md).toContain('Open Questions');
    expect(md).toContain('Sources');
  });

  it('omits sections when requested', () => {
    const md = buildMarkdownFromPhase(0, 5, 'Synthesis', {
      critical_insights: ['Should be omitted'],
      action_blueprint: ['Also omitted'],
      open_questions: ['Still omitted'],
      sources: [{ title: 'Omitted too', url: 'https://x.com' }],
    }, {
      omitSections: ['critical_insights', 'action_blueprint', 'open_questions', 'sources'],
    });
    expect(md).not.toContain('Critical Insights');
    expect(md).not.toContain('Action Blueprint');
    expect(md).not.toContain('Open Questions');
    expect(md).not.toContain('Sources');
  });

  it('handles missing candidate content gracefully', () => {
    const md = buildMarkdownFromPhase(0, 2, 'Perspectives', {
      candidates: [
        { perspective: 'Minimal', model_used: 'gemini-flash' },
        // no content, no key_insights
      ],
    });
    expect(md).toContain('Minimal');
    expect(md).not.toContain('undefined');
  });

  it('renders deep read vetted context', () => {
    const md = buildMarkdownFromPhase(0, 1.5, 'Deep Read', {
      vetted_context: [
        {
          title: 'Source A',
          url: 'https://a.com',
          date: '2026-01-01',
          summary: 'Important findings',
          key_facts: ['Fact 1', 'Fact 2'],
        },
      ],
    });
    expect(md).toContain('Source A');
    expect(md).toContain('2026-01-01');
    expect(md).toContain('Fact 1');
  });

  it('renders web discovery results', () => {
    const md = buildMarkdownFromPhase(0, 0, 'Search', {
      web_discovery_results: [
        { title: 'Article', url: 'https://example.com', snippet: 'A snippet' },
      ],
    });
    expect(md).toContain('Sources Discovered');
    expect(md).toContain('Article');
    expect(md).toContain('snippet');
  });
});


describe('buildMarkdownFromPhases — edge cases', () => {
  it('handles empty phases array', () => {
    const md = buildMarkdownFromPhases([]);
    expect(md).toBe('');
  });

  it('builds from multiple phases', () => {
    const md = buildMarkdownFromPhases([
      { phase: 1, name: 'Phase 1', data: { solution: 'Hello' } },
      { phase: 2, name: 'Phase 2', data: { solution: 'World' } },
    ]);
    expect(md).toContain('Hello');
    expect(md).toContain('World');
    expect(md).toContain('---');
  });

  it('separates phases with horizontal rule', () => {
    const md = buildMarkdownFromPhases([
      { phase: 1, name: 'A', data: { solution: 'x' } },
      { phase: 2, name: 'B', data: { solution: 'y' } },
    ]);
    const sections = md.split('---');
    expect(sections.length).toBeGreaterThanOrEqual(2);
  });
});


describe('Markdown builder — XSS prevention', () => {
  it('passes through HTML-like content without sanitization (data is trusted LLM output)', () => {
    // The markdown builder is a formatting layer, not a sanitizer.
    // It renders LLM output as-is. This test verifies consistent behavior.
    const md = buildMarkdownFromPhase(0, 5, 'Synthesis', {
      solution: 'Normal text with <script>alert("xss")</script> in content',
    });
    // React-Markdown will later handle rendering; our formatter just passes through
    expect(md).toContain('<script>');
  });

  it('does not crash on deeply nested data', () => {
    const deep: any = { solution: 'ok' };
    let current = deep;
    for (let i = 0; i < 100; i++) {
      current.nested = { solution: 'still ok' };
      current = current.nested;
    }
    const md = buildMarkdownFromPhase(0, 5, 'Synthesis', deep);
    expect(md).toContain('ok');
  });

  it('does not crash on circular references in data', () => {
    const circular: any = { solution: 'before loop' };
    circular.self = circular;
    const md = buildMarkdownFromPhase(0, 5, 'Synthesis', circular);
    expect(md).toContain('before loop');
  });
});


describe('Markdown builder — phase state types', () => {
  it('renders CoVE state', () => {
    const md = buildMarkdownFromPhase(0, 3, 'CoVE', {
      cove_state: {
        draft_answer: 'Initial answer.',
        claims: ['Claim 1', 'Claim 2'],
        verification_questions: [{ question: 'Is Claim 1 true?' }],
        verification_answers: [{ answer: 'Yes', question: 'Is Claim 1 true?' }],
        revised_answer: 'Revised answer.',
        changes_made: ['Removed Claim 2'],
        remaining_uncertainties: ['Uncertainty 1'],
      },
    });
    expect(md).toContain('Draft Answer');
    expect(md).toContain('Initial answer');
    expect(md).toContain('Claims');
    expect(md).toContain('Verification Questions');
    expect(md).toContain('Revised Answer');
  });

  it('renders debate state', () => {
    const md = buildMarkdownFromPhase(0, 2, 'Debate', {
      debate_rounds: [
        {
          round: 'Round 1',
          type: 'opening',
          statements: [
            { side: 'Pro', content: 'Argument 1' },
            { side: 'Con', content: 'Counter 1' },
          ],
        },
      ],
    });
    expect(md).toContain('Debate Rounds');
    expect(md).toContain('Pro');
    expect(md).toContain('Con');
    expect(md).toContain('Argument 1');
  });

  it('renders empty debate state gracefully', () => {
    const md = buildMarkdownFromPhase(0, 2, 'Debate', {
      debate_rounds: [],
    });
    expect(md).toContain('No content');
    expect(md).not.toContain('undefined');
  });
});
