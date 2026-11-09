// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

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
      onToggleTheme={noop}
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

  it('leaves the open palette interactive', () => {
    renderPalette(true);
    const input = screen.getByPlaceholderText('Type a command...');
    expect(input.closest('[inert]')).toBeNull();
  });
});
