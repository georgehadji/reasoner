// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

vi.mock('@/hooks/useFeatureFlags', () => ({ isEnabled: () => true }));

import { ContinueButton } from './ChatFeed';

describe('ContinueButton', () => {
  // It only submits "Continue" through the normal composer path, which an
  // anonymous caller can already use by typing. Disabling it behind sign-in
  // blocked nothing the server refuses and broke local, sign-in-free use.
  it('works without a signed-in user', () => {
    const onContinue = vi.fn();
    render(<ContinueButton onContinue={onContinue} />);

    const button = screen.getByRole('button', { name: /continue reasoning/i });
    expect(button).toBeEnabled();
    fireEvent.click(button);
    expect(onContinue).toHaveBeenCalledOnce();
    expect(screen.queryByText(/sign in/i)).toBeNull();
  });
});
