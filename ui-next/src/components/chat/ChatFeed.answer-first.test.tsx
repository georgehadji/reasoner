// @vitest-environment jsdom
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

vi.mock('@/hooks/useFeatureFlags', () => ({ isEnabled: () => true }));

const copied: string[] = [];
vi.mock('@/lib/utils', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/utils')>();
  return {
    ...actual,
    copyToClipboard: vi.fn(async (text: string) => {
      copied.push(text);
      return true;
    }),
  };
});

import { ChatFeed, type ChatFeedMessage, type RenderedPhase } from './ChatFeed';

const noop = () => {};

const phases: RenderedPhase[] = [
  { index: 0, phase: 0, name: 'Classification', data: { task_type: 'strategy', rationale: 'Planning', language: 'English' } },
  { index: 1, phase: 1, name: 'Decomposition', data: { sub_problems: [{ id: '1', description: 'Market' }], assumptions: [] } },
  {
    index: 2,
    phase: 5,
    name: 'Synthesis',
    data: {
      core_solution: 'Ship the small version first.',
      action_blueprint: [{ step: 'Week 1', action: 'Cut scope' }],
    },
  },
];

const run = (overrides: Partial<ChatFeedMessage> = {}): ChatFeedMessage[] => [
  { id: 'u1', role: 'user', content: 'How should we launch?' },
  {
    id: 'a1',
    role: 'assistant',
    content: '# Phase 1: Classification\n\nfull run dump',
    phases,
    isStreaming: false,
    ...overrides,
  },
];

function renderFeed(messages: ChatFeedMessage[]) {
  return render(<ChatFeed messages={messages} onScrollToBottom={noop} showNewContentIndicator={false} />);
}

beforeEach(() => {
  copied.length = 0;
});

describe('ChatFeed — a finished run shows the answer first', () => {
  it('puts the answer above the collapsed process', () => {
    renderFeed(run());

    const answer = screen.getByRole('region', { name: /answer/i });
    const toggle = screen.getByRole('button', { name: /how this was reached/i });
    expect(within(answer).getByText('Ship the small version first.')).toBeInTheDocument();
    // DOCUMENT_POSITION_FOLLOWING: the toggle comes after the answer.
    expect(answer.compareDocumentPosition(toggle) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
  });

  it('shows a one-line summary of the run and opens to one row per phase', () => {
    renderFeed(run());

    const toggle = screen.getByRole('button', { name: /how this was reached/i });
    expect(toggle).toHaveTextContent('3 phases');
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');

    const process = screen.getByRole('region', { name: /how this was reached/i });
    expect(within(process).getByText('Classification')).toBeInTheDocument();
    expect(within(process).getByText('Decomposition')).toBeInTheDocument();
    // Level 1 says what the phase found, level 2 (the card body) stays shut.
    expect(within(process).getByText('strategy · English')).toBeInTheDocument();
    expect(within(process).getByRole('button', { name: /classification/i })).toHaveAttribute('aria-expanded', 'false');
  });

  it('keeps pipeline order while the run is still streaming', () => {
    renderFeed(run({ isStreaming: true }));

    expect(screen.queryByRole('button', { name: /how this was reached/i })).toBeNull();
    expect(screen.queryByRole('region', { name: /^answer$/i })).toBeNull();
  });

  it('copies the answer alone, and the full run on request', async () => {
    renderFeed(run());

    fireEvent.click(screen.getByRole('button', { name: /copy answer/i }));
    await vi.waitFor(() => expect(copied).toHaveLength(1));
    expect(copied[0]).toContain('Ship the small version first.');
    expect(copied[0]).not.toContain('full run dump');

    fireEvent.click(screen.getByRole('button', { name: /copy full run/i }));
    await vi.waitFor(() => expect(copied).toHaveLength(2));
    expect(copied[1]).toBe('# Phase 1: Classification\n\nfull run dump');
  });
});

describe('ChatFeed — an article run reads as a document', () => {
  const article = '# Burnout at Work\n\n## Why it happens\n\nLong hours.\n\n## What helps\n\nRest.\n\n## Next steps\n\nAct.';
  const articlePhases: RenderedPhase[] = [
    { index: 0, phase: 0, name: 'Classification', data: { task_type: 'writing', rationale: 'Article' } },
    { index: 1, phase: 4, name: 'Final Polish', data: { writing_state: { final_article: article, outline: [{ heading: 'Draft outline' }] } } },
  ];

  it('renders the article with a contents list, without the drafting log', () => {
    renderFeed([
      { id: 'u1', role: 'user', content: 'Write about burnout' },
      { id: 'a1', role: 'assistant', content: 'dump', phases: articlePhases, isStreaming: false },
    ]);

    const answer = screen.getByRole('region', { name: /answer/i });
    expect(within(answer).getByRole('heading', { level: 1, name: 'Burnout at Work' })).toBeInTheDocument();
    const contents = within(answer).getByRole('navigation', { name: /contents/i });
    expect(within(contents).getByRole('link', { name: 'What helps' })).toHaveAttribute('href', '#what-helps');
    expect(within(answer).queryByText('Draft outline')).toBeNull();
  });

  it('offers the article as a Markdown download', () => {
    renderFeed([
      { id: 'u1', role: 'user', content: 'Write about burnout' },
      { id: 'a1', role: 'assistant', content: 'dump', phases: articlePhases, isStreaming: false },
    ]);

    expect(screen.getByRole('button', { name: /download answer as markdown/i })).toBeInTheDocument();
  });
});
