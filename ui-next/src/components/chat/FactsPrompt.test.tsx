import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FactsPrompt } from './FactsPrompt';

const QUESTIONS = ['What is the person\'s age?', 'Which medicines are they taking?'];

function renderPrompt() {
  const onSubmit = vi.fn();
  render(<FactsPrompt questions={QUESTIONS} onSubmit={onSubmit} onCancel={vi.fn()} />);
  return onSubmit;
}

describe('FactsPrompt', () => {
  it('labels one input per question, capped at 200 characters, and focuses the first', () => {
    renderPrompt();
    const first = screen.getByLabelText(QUESTIONS[0]) as HTMLInputElement;
    expect(first.maxLength).toBe(200);
    expect(screen.getByLabelText(QUESTIONS[1])).toBeTruthy();
    expect(document.activeElement).toBe(first);
    expect(screen.getByRole('group', { name: /more reliable/ })).toBeTruthy();
  });

  it('sends only the non-empty answers, keyed by question', () => {
    const onSubmit = renderPrompt();
    fireEvent.change(screen.getByLabelText(QUESTIONS[0]), { target: { value: ' 34 ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Answer and continue' }));
    expect(onSubmit).toHaveBeenCalledWith({ [QUESTIONS[0]]: '34' });
  });

  it('Enter in a field submits the answers', () => {
    const onSubmit = renderPrompt();
    fireEvent.change(screen.getByLabelText(QUESTIONS[1]), { target: { value: 'none' } });
    fireEvent.submit(screen.getByRole('group'));
    expect(onSubmit).toHaveBeenCalledWith({ [QUESTIONS[1]]: 'none' });
  });

  it('skip sends no facts even when fields are filled', () => {
    const onSubmit = renderPrompt();
    fireEvent.change(screen.getByLabelText(QUESTIONS[0]), { target: { value: '34' } });
    fireEvent.click(screen.getByRole('button', { name: 'Skip and answer anyway' }));
    expect(onSubmit).toHaveBeenCalledWith({});
  });
});
