"""The launcher's port helpers must not report a failed check as a result.

P5, docs/plans/root-cause-remediation-2026-09-07.md.

``start_all.py`` had five ``except Exception`` swallows. Three of them turn a
failed *check* into a confident answer:

- ``_port_in_use`` returned "the port is free" when the probe itself raised.
- both PID lookups left ``pid`` at None, and the caller prints
  ``"zombie socket"`` for a None pid -- so a failed ``netstat``/``lsof`` told
  the reader there was no process to stop when there was one.

The fourth, ``_wait_for_health``, is the opposite case: connection-refused is
the expected state for most of the poll, so it still passes -- but it now
catches ``OSError`` rather than everything, so a bug in the poll itself is no
longer eaten for the full 30s and then reported as "the server never started".
"""

from __future__ import annotations

import socket
import subprocess

import pytest

from reasoner import start_all


def test_a_failed_probe_is_not_reported_as_a_free_port(monkeypatch, capsys):
    def _boom(*args, **kwargs):
        raise OSError("no socket for you")

    monkeypatch.setattr(socket, "socket", _boom)

    in_use, pid = start_all._port_in_use(8003)

    assert (in_use, pid) == (False, None)
    assert "Could not probe port 8003" in capsys.readouterr().out


def test_a_failed_pid_lookup_says_so(monkeypatch, capsys):
    """A None pid makes the caller print 'zombie socket'. Say why it is None."""
    class _Connected:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def settimeout(self, _t):
            pass

        def connect_ex(self, _addr):
            return 0  # 0 == connected == port is in use

    monkeypatch.setattr(socket, "socket", lambda *a, **kw: _Connected())
    monkeypatch.setattr(
        subprocess, "check_output",
        lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError("netstat")),
    )

    in_use, pid = start_all._port_in_use(8003)

    assert in_use is True
    assert pid is None
    assert "Could not identify the owner of port 8003" in capsys.readouterr().out


def test_the_health_poll_does_not_eat_its_own_bugs(monkeypatch):
    """Only OSError means 'not up yet'. Anything else is our bug, not theirs."""
    import urllib.request

    def _bug(*args, **kwargs):
        raise ValueError("malformed poll URL")

    monkeypatch.setattr(urllib.request, "urlopen", _bug)

    with pytest.raises(ValueError):
        start_all._wait_for_health(8003, timeout=1.0)


def test_the_health_poll_still_tolerates_a_server_that_is_not_up(monkeypatch):
    import urllib.request

    def _refused(*args, **kwargs):
        raise ConnectionRefusedError("not listening yet")

    monkeypatch.setattr(urllib.request, "urlopen", _refused)
    monkeypatch.setattr(start_all.time, "sleep", lambda _s: None)

    assert start_all._wait_for_health(8003, timeout=0.2) is False
