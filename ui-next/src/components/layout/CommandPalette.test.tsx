// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock('@/hooks/useFeatureFlags', () => ({ isEnabled: () => true }));

import { CommandPalette } from './CommandPalette';

const noop = () => {};
const renderPalette = (isOpen: boolean) =>
  render(
    <CommandPalette
      isOpen={isOpen}
      onClose={noop}
      onNew={noop}
      onClearComposer={noop}
      onToggleSidebar={noop}
      onToggleNeuro={noop}
      onToggleTier={noop}
      tier="budget"
      onCopyLastResponse={noop}
    />,
  );

describe('CommandPalette', () => {
  // The closed palette stays mounted (only faded out) so it can animate, and its
  // input was still a Tab stop: keyboard users landed on a field they could not see.
  it('takes the closed palette out of focus and the accessibility tree', () => {
    renderPalette(false);
    const input = screen.getByPlaceholderText('Type a command...');
    expect(input.closest('[inert]')).not.toBeNull();
  });

  // Closing made the focused input inert, so keyboard focus fell to <body>.
  it('returns focus to whatever opened it when it closes', async () => {
    const opener = document.createElement('button');
    document.body.appendChild(opener);
    opener.focus();
    const props = {
      onClose: noop, onNew: noop, onClearComposer: noop, onToggleSidebar: noop,
      onToggleNeuro: noop, onToggleTier: noop, tier: 'budget', onCopyLastResponse: noop,
    };
    const { rerender } = render(<CommandPalette isOpen {...props} />);
    const input = screen.getByRole('textbox', { name: 'Search commands' });
    await waitFor(() => expect(document.activeElement).toBe(input));

    rerender(<CommandPalette isOpen={false} {...props} />);
    expect(document.activeElement).toBe(opener);
    opener.remove();
  });

  it('leaves the open palette interactive', () => {
    renderPalette(true);
    const input = screen.getByPlaceholderText('Type a command...');
    expect(input.closest('[inert]')).toBeNull();
  });
});
