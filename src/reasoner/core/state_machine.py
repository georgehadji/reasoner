"""One shape for every lifecycle: a state enum, a transition table, this checker.

docs/plans/implicit-state-machines-2026-11-11.md §0 records the decision: no
state-machine library, one declarative table per lifecycle, checked here. A
machine starts in observe mode (an illegal move is logged and counted, then
allowed, so nothing that works today breaks) and is switched to enforce mode
once ``reasoner_illegal_transition_total`` has stayed at zero for a release.

    class RunState(StrEnum):
        RUNNING = "running"
        DONE = "done"

    RUN = Machine("run", {RunState.RUNNING: {RunState.DONE}, RunState.DONE: set()},
                  initial=RunState.RUNNING)
    state = RUN.move(state, RunState.DONE)

A state whose allowed set is empty is terminal. A self-loop is legal only when
the table lists it. Every machine registers itself by name, which is how the
contract test and the generated docs find it.
"""

from __future__ import annotations

import logging
from collections.abc import Hashable, Iterable, Mapping

from reasoner.core.exceptions import InvalidTransitionError
from reasoner.core.ports.metrics_port import count_illegal_transition

logger = logging.getLogger(__name__)

_REGISTRY: dict[str, Machine] = {}


def _name(state: object) -> str:
    return str(getattr(state, "value", state))


class Machine[S: Hashable]:
    """A transition table plus the one function allowed to read it."""

    def __init__(
        self,
        name: str,
        transitions: Mapping[S, Iterable[S]],
        *,
        initial: S,
        enforce: bool = False,
    ) -> None:
        table = {src: frozenset(dsts) for src, dsts in transitions.items()}
        missing = {d for dsts in table.values() for d in dsts} | {initial}
        missing -= table.keys()
        if missing:
            raise ValueError(f"machine {name!r}: states with no row: {sorted(map(_name, missing))}")
        if name in _REGISTRY:
            raise ValueError(f"machine {name!r} is already registered")
        self.name = name
        self.initial = initial
        self.enforce = enforce
        self._table: dict[S, frozenset[S]] = table
        _REGISTRY[name] = self

    @property
    def states(self) -> frozenset[S]:
        return frozenset(self._table)

    @property
    def terminal(self) -> frozenset[S]:
        return frozenset(s for s, dsts in self._table.items() if not dsts)

    def allowed_from(self, current: S) -> frozenset[S]:
        return self._table.get(current, frozenset())

    def can(self, current: S, target: S) -> bool:
        return target in self.allowed_from(current)

    def move(self, current: S, target: S) -> S:
        """Return ``target`` if the table allows the move.

        An illegal move raises ``InvalidTransitionError`` when enforcing. When
        observing it is logged and counted, and ``target`` is still returned,
        so adopting a machine never changes behaviour on its own.
        """
        if self.can(current, target):
            return target
        src, dst = _name(current), _name(target)
        if self.enforce:
            raise InvalidTransitionError(
                f"{self.name}: illegal move {src} -> {dst}",
                {"machine": self.name, "from": src, "to": dst},
            )
        logger.warning("illegal transition in %s: %s -> %s (observe mode)", self.name, src, dst)
        count_illegal_transition(self.name, src, dst)
        return target

    def to_mermaid(self) -> str:
        """The table as a Mermaid ``stateDiagram-v2``: docs are generated, never drawn."""
        lines = ["stateDiagram-v2", f"    [*] --> {_name(self.initial)}"]
        for src in sorted(self._table, key=_name):
            for dst in sorted(self._table[src], key=_name):
                lines.append(f"    {_name(src)} --> {_name(dst)}")
            if not self._table[src]:
                lines.append(f"    {_name(src)} --> [*]")
        return "\n".join(lines)


def registered_machines() -> dict[str, Machine]:
    """Every machine constructed so far, by name. A copy: callers cannot unregister."""
    return dict(_REGISTRY)


def unregister(name: str) -> None:
    """Drop a machine. For tests that build throwaway machines; production never calls it."""
    _REGISTRY.pop(name, None)
