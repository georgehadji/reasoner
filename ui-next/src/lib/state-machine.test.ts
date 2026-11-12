import { afterEach, describe, expect, it, vi } from 'vitest';

import { defineMachine, InvalidTransitionError, type Machine } from './state-machine';

type Door = 'open' | 'closed' | 'gone';

const door = () =>
  defineMachine<Door>('test.door', { open: ['closed'], closed: ['open', 'gone'], gone: [] }, 'open');

/** Mirrors tests/architecture/test_state_machines.py::_check_sound. */
function checkSound<S extends string>(m: Machine<S>): void {
  const seen = new Set<S>([m.initial]);
  const todo: S[] = [m.initial];
  while (todo.length) {
    for (const next of m.allowedFrom(todo.pop()!)) {
      if (!seen.has(next)) {
        seen.add(next);
        todo.push(next);
      }
    }
  }
  expect([...seen].sort(), `${m.name}: orphan states`).toEqual([...m.states].sort());
  expect(m.states.some((s) => m.allowedFrom(s).length === 0), `${m.name}: no terminal`).toBe(true);
}

describe('defineMachine', () => {
  afterEach(() => vi.unstubAllEnvs());

  it('passes the soundness contract', () => {
    checkSound(door());
  });

  it('allows every listed edge and throws on every other one under test', () => {
    const m = door();
    for (const from of m.states) {
      for (const to of m.states) {
        if (m.can(from, to)) expect(m.move(from, to)).toBe(to);
        else expect(() => m.move(from, to)).toThrow(InvalidTransitionError);
      }
    }
  });

  it('carries the machine and edge on the error', () => {
    expect(() => door().move('gone', 'open')).toThrow(
      expect.objectContaining({ machine: 'test.door', from: 'gone', to: 'open' }),
    );
  });

  it('warns and allows an illegal move in development', () => {
    vi.stubEnv('NODE_ENV', 'development');
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    expect(door().move('gone', 'open')).toBe('open');
    expect(warn).toHaveBeenCalledWith('[state-machine] test.door: illegal move gone -> open');
    warn.mockRestore();
  });

  it('allows an illegal move silently in production', () => {
    vi.stubEnv('NODE_ENV', 'production');
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    expect(door().move('gone', 'open')).toBe('open');
    expect(warn).not.toHaveBeenCalled();
    warn.mockRestore();
  });

  it('flags an orphan state', () => {
    const orphan = defineMachine<Door>('test.orphan', { open: [], closed: ['gone'], gone: [] }, 'open');
    expect(() => checkSound(orphan)).toThrow(/orphan/);
  });
});
