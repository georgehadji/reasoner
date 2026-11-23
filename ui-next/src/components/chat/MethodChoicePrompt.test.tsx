import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MethodChoicePrompt } from './MethodChoicePrompt';
import type { GateResponse } from '@/lib/types';

function decision(overrides: Partial<GateResponse>): GateResponse {
  return {
    method: 'multi_perspective',
    preset: 'multi-perspective-budget',
    confidence: 0.42,
    reasoning: 'Trade-offs between options',
    alternatives: [],
    ...overrides,
  } as GateResponse;
}

function renderPrompt(d: GateResponse) {
  return render(
    <MethodChoicePrompt
      decision={d}
      alwaysAuto={false}
      onChoose={vi.fn()}
      onToggleAlwaysAuto={vi.fn()}
      onCancel={vi.fn()}
    />,
  );
}

describe('MethodChoicePrompt', () => {
  it('focuses the suggested method so Enter confirms it', () => {
    renderPrompt(decision({}));
    expect(document.activeElement).toBe(screen.getByRole('button', { name: /Multi-Perspective/ }));
  });

  it('shows confidence and rationale for a real classification', () => {
    renderPrompt(decision({}));
    expect(screen.getByText('42% confidence')).toBeTruthy();
    expect(screen.getByText('Trade-offs between options')).toBeTruthy();
  });

  it('hides the internal fallback note when the gate could not classify', () => {
    renderPrompt(
      decision({ confidence: 0, reasoning: 'All sub-agents failed or returned very low confidence, fallback' }),
    );
    expect(screen.queryByText(/confidence/)).toBeNull();
    expect(screen.queryByText(/sub-agents failed/)).toBeNull();
  });
});
