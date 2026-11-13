// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useKeyboardShortcuts } from './useKeyboardShortcuts';

const pressEscapeOn = (el: HTMLElement) =>
  el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));

afterEach(() => {
  document.body.innerHTML = '';
});

describe('useKeyboardShortcuts Escape', () => {
  it('stops the run when Escape is pressed outside a dialog', () => {
    const onStop = vi.fn();
    renderHook(() => useKeyboardShortcuts({ onStop }));
    pressEscapeOn(document.body);
    expect(onStop).toHaveBeenCalledTimes(1);
  });

  it('does not stop the run when Escape closes an open <dialog>', () => {
    const onStop = vi.fn();
    renderHook(() => useKeyboardShortcuts({ onStop }));
    const dialog = document.createElement('dialog');
    dialog.setAttribute('open', '');
    const button = document.createElement('button');
    dialog.appendChild(button);
    document.body.appendChild(dialog);
    pressEscapeOn(button);
    expect(onStop).not.toHaveBeenCalled();
  });

  it('does not stop the run when Escape is pressed inside a role="dialog" overlay', () => {
    const onStop = vi.fn();
    renderHook(() => useKeyboardShortcuts({ onStop }));
    const palette = document.createElement('div');
    palette.setAttribute('role', 'dialog');
    const input = document.createElement('input');
    palette.appendChild(input);
    document.body.appendChild(palette);
    pressEscapeOn(input);
    expect(onStop).not.toHaveBeenCalled();
  });
});
