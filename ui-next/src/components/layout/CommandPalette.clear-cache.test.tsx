// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock('@/hooks/useFeatureFlags', () => ({ isEnabled: () => true }));

import { CommandPalette } from './CommandPalette';

const noop = () => {};

describe('CommandPalette — Clear server cache', () => {
  // Moved out of the sidebar footer, where it sat next to Memory as a one-click
  // destructive action and, on a phone, under the Next dev badge.
  it('offers the command and runs it', () => {
    const onClearCache = vi.fn();
    render(
      <CommandPalette
        isOpen
        onClose={noop}
        onNew={noop}
        onClearComposer={noop}
        onToggleSidebar={noop}
        onToggleNeuro={noop}
        onToggleTier={noop}
        tier="budget"
        onCopyLastResponse={noop}
        onClearCache={onClearCache}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /clear server cache/i }));
    expect(onClearCache).toHaveBeenCalledOnce();
  });
});
