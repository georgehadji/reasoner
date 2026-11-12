"""Every lifecycle in the app is a `core.state_machine.Machine`, and every one is sound.

A module that builds a Machine is found by grepping `src/` for the import, so a
new machine is covered the moment it is written; nothing has to be registered
by hand. The checks are the plan's (docs/plans/implicit-state-machines-2026-11-11.md
Phase 2, step 3): no orphan state, a reachable terminal state, every enum member
in the table, and every edge, legal or not, behaves as the table says.
"""

from __future__ import annotations

import importlib
import logging
from enum import Enum, StrEnum
from pathlib import Path

import pytest

from reasoner.core.exceptions import InvalidTransitionError
from reasoner.core.ports import metrics_port
from reasoner.core.state_machine import Machine, registered_machines, unregister

pytestmark = pytest.mark.unit

SRC = Path(__file__).resolve().parents[2] / "src"
_IMPORT = "reasoner.core.state_machine"


def _machine_modules() -> list[str]:
    own = SRC / "reasoner" / "core" / "state_machine.py"
    return sorted(
        ".".join(p.relative_to(SRC).with_suffix("").parts)
        for p in (SRC / "reasoner").rglob("*.py")
        if p != own and _IMPORT in p.read_text(encoding="utf-8", errors="ignore")
    )


def _app_machines() -> list[Machine]:
    for mod in _machine_modules():
        importlib.import_module(mod)
    return [m for n, m in sorted(registered_machines().items()) if not n.startswith("test.")]


def _reachable(m: Machine) -> set:
    seen, todo = {m.initial}, [m.initial]
    while todo:
        for nxt in m.allowed_from(todo.pop()):
            if nxt not in seen:
                seen.add(nxt)
                todo.append(nxt)
    return seen


def _check_sound(m: Machine) -> None:
    reachable = _reachable(m)
    assert reachable == m.states, f"{m.name}: orphan states {m.states - reachable}"
    assert m.terminal & reachable, f"{m.name}: no reachable terminal state"
    if isinstance(m.initial, Enum):
        assert set(type(m.initial)) == m.states, f"{m.name}: enum members missing from the table"


# ── The app's machines (none yet: Phase 3 adds them) ─────────────────────────

APP_MACHINES = _app_machines()


@pytest.mark.parametrize("machine", APP_MACHINES, ids=lambda m: m.name)
def test_app_machine_is_sound(machine):
    _check_sound(machine)


@pytest.mark.parametrize("machine", APP_MACHINES, ids=lambda m: m.name)
def test_enforcing_app_machine_raises_on_every_illegal_edge(machine):
    if not machine.enforce:
        pytest.skip("observe mode: illegal moves are counted, not raised")
    for src in machine.states:
        for dst in machine.states:
            if machine.can(src, dst):
                assert machine.move(src, dst) == dst
            else:
                with pytest.raises(InvalidTransitionError):
                    machine.move(src, dst)


# ── The helper itself ────────────────────────────────────────────────────────

class _Door(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    GONE = "gone"


_DOOR_TABLE = {
    _Door.OPEN: {_Door.CLOSED},
    _Door.CLOSED: {_Door.OPEN, _Door.GONE},
    _Door.GONE: set(),
}


@pytest.fixture
def door():
    made: list[str] = []

    def build(*, enforce: bool, name: str = "test.door") -> Machine:
        made.append(name)
        return Machine(name, _DOOR_TABLE, initial=_Door.OPEN, enforce=enforce)

    yield build
    for name in made:
        unregister(name)


@pytest.fixture
def sink():
    """Swap the counter sink for one test, then put the real one back."""
    previous = metrics_port._ILLEGAL_TRANSITION_COUNTER
    yield metrics_port.set_illegal_transition_counter
    metrics_port.set_illegal_transition_counter(previous)


@pytest.fixture
def counted(sink):
    seen: list[tuple[str, str, str]] = []
    sink(lambda *a: seen.append(a))
    return seen


def test_sound_helper_machine_passes_the_contract(door):
    _check_sound(door(enforce=True))


@pytest.mark.parametrize("src", list(_Door))
@pytest.mark.parametrize("dst", list(_Door))
def test_enforcing_machine_raises_on_every_illegal_edge(door, src, dst):
    m = door(enforce=True)
    if dst in _DOOR_TABLE[src]:
        assert m.move(src, dst) is dst
    else:
        with pytest.raises(InvalidTransitionError) as exc:
            m.move(src, dst)
        assert exc.value.details == {"machine": "test.door", "from": src.value, "to": dst.value}


def test_observing_machine_counts_and_allows_an_illegal_move(door, counted, caplog):
    with caplog.at_level(logging.WARNING, logger="reasoner.core.state_machine"):
        assert door(enforce=False).move(_Door.GONE, _Door.OPEN) is _Door.OPEN
    assert counted == [("test.door", "gone", "open")]
    assert "gone -> open" in caplog.text


def test_legal_move_is_not_counted(door, counted):
    door(enforce=False).move(_Door.OPEN, _Door.CLOSED)
    assert counted == []


def test_broken_counter_does_not_break_the_move(door, sink):
    def boom(*_a):
        raise RuntimeError("metrics down")

    sink(boom)
    assert door(enforce=False).move(_Door.GONE, _Door.OPEN) is _Door.OPEN


def test_table_with_a_target_but_no_row_is_refused():
    with pytest.raises(ValueError, match="no row"):
        Machine("test.bad", {_Door.OPEN: {_Door.CLOSED}}, initial=_Door.OPEN)
    assert "test.bad" not in registered_machines()


def test_duplicate_name_is_refused(door):
    door(enforce=False)
    with pytest.raises(ValueError, match="already registered"):
        Machine("test.door", _DOOR_TABLE, initial=_Door.OPEN)


def test_orphan_state_fails_the_contract():
    m = Machine("test.orphan", {**_DOOR_TABLE, _Door.OPEN: set()}, initial=_Door.OPEN)
    try:
        with pytest.raises(AssertionError, match="orphan"):
            _check_sound(m)
    finally:
        unregister("test.orphan")


def test_mermaid_lists_every_edge_and_terminal(door):
    assert door(enforce=False).to_mermaid().splitlines() == [
        "stateDiagram-v2",
        "    [*] --> open",
        "    closed --> gone",
        "    closed --> open",
        "    gone --> [*]",
        "    open --> closed",
    ]


def test_prometheus_counter_is_wired():
    # Importing infrastructure.metrics installs the sink, as for the degradation counter.
    import reasoner.infrastructure.metrics  # noqa: F401

    assert metrics_port._ILLEGAL_TRANSITION_COUNTER is not None
