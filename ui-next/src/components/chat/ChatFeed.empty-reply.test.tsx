// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('@/hooks/useFeatureFlags', () => ({ isEnabled: () => true }));

import { ChatFeed, type ChatFeedMessage } from './ChatFeed';

const noop = () => {};

describe('ChatFeed — a run that failed before any reply', () => {
  // The streaming placeholder stayed behind empty, with its Copy button, so
  // "Copy" sat between the prompt and the error and copied nothing.
  it('shows no empty reply and no Copy button', () => {
    const messages: ChatFeedMessage[] = [
      { id: 'u1', role: 'user', content: 'Write an article about AI burnout' },
      { id: 'a1', role: 'assistant', content: '', isStreaming: false },
      { id: 'e1', role: 'error', content: 'Pipeline error' },
    ];
    render(<ChatFeed messages={messages} onScrollToBottom={noop} showNewContentIndicator={false} />);

    expect(screen.queryByRole('button', { name: /copy response/i })).toBeNull();
    expect(screen.getByText('Pipeline error')).toBeInTheDocument();
  });

  it('keeps Copy on a reply that has content', () => {
    const messages: ChatFeedMessage[] = [
      { id: 'u1', role: 'user', content: 'Capital of France?' },
      { id: 'a1', role: 'assistant', content: 'Paris.', isStreaming: false },
    ];
    render(<ChatFeed messages={messages} onScrollToBottom={noop} showNewContentIndicator={false} />);

    expect(screen.getByRole('button', { name: /copy response/i })).toBeInTheDocument();
  });
});
