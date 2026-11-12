/**
 * One shape for every UI lifecycle: a string union of states, a transition table,
 * this checker. The TypeScript twin of `src/reasoner/core/state_machine.py`
 * (docs/plans/implicit-state-machines-2026-11-11.md §0): no state-machine library.
 *
 *   type Run = 'idle' | 'running' | 'stopping';
 *   const RUN = defineMachine<Run>('chat.run', {
 *     idle: ['running'], running: ['stopping', 'idle'], stopping: ['idle', 'running'],
 *   }, 'idle');
 *   // in a reducer: return { ...state, status: RUN.move(state.status, 'running') };
 *
 * An illegal move throws under vitest, so a test catches it; elsewhere it warns
 * in development and is allowed, so adopting a machine never changes what a
 * user sees. A state with an empty list is terminal.
 */

export class InvalidTransitionError extends Error {
  constructor(
    readonly machine: string,
    readonly from: string,
    readonly to: string,
  ) {
    super(`${machine}: illegal move ${from} -> ${to}`);
    this.name = 'InvalidTransitionError';
  }
}

export interface Machine<S extends string> {
  readonly name: string;
  readonly initial: S;
  readonly states: readonly S[];
  allowedFrom(from: S): readonly S[];
  can(from: S, to: S): boolean;
  move(from: S, to: S): S;
}

export function defineMachine<S extends string>(
  name: string,
  transitions: Record<S, readonly S[]>,
  initial: S,
): Machine<S> {
  const states = Object.keys(transitions) as S[];
  const can = (from: S, to: S) => transitions[from]?.includes(to) ?? false;
  return {
    name,
    initial,
    states,
    allowedFrom: (from) => transitions[from] ?? [],
    can,
    move(from, to) {
      if (can(from, to)) return to;
      if (process.env.NODE_ENV === 'test') throw new InvalidTransitionError(name, from, to);
      if (process.env.NODE_ENV !== 'production') {
        console.warn(`[state-machine] ${name}: illegal move ${from} -> ${to}`);
      }
      return to;
    },
  };
}
