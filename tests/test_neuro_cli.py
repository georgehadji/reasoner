"""cli.py's `status` and `start` commands reach the exact same require_neuro_key
-gated router as the HTTP API and the standalone-app production checks in
api/__init__.py -- but as separate entry points, neither of those gates
applied to them for free. These tests guard both fixes.
"""

import click.testing
import pytest

import reasoner.neuro.cli as cli


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or str(payload)

    def json(self):
        return self._payload


@pytest.fixture
def runner():
    return click.testing.CliRunner()


def test_status_sends_the_internal_key_header(runner, monkeypatch):
    """/api/neuro/health is gated by require_neuro_key like every other
    /api/neuro/* route. Without this header, status() 403s against any
    deployment that has NEURO_INTERNAL_KEY set (required in production)."""
    monkeypatch.setenv("NEURO_INTERNAL_KEY", "the-shared-key")
    captured = {}

    def fake_get(url, timeout=5.0, headers=None):
        captured["headers"] = headers
        return _FakeResponse(
            200,
            {
                "status": "ok",
                "version": "x",
                "reasoning": {},
                "embedding": {},
                "sessions": {},
            },
        )

    monkeypatch.setattr(cli.httpx, "get", fake_get)
    result = runner.invoke(cli.main, ["status"])

    assert captured.get("headers") == {"X-Neuro-Key": "the-shared-key"}
    assert result.exit_code == 0


def test_status_reports_a_gated_response_instead_of_a_confusing_error(runner, monkeypatch):
    """Before: a 403 (or any non-200) fell through to resp.json()/data['status'],
    which either KeyErrors or misreports a reachable-but-gated server as
    unreachable via the broad except-Exception branch."""
    monkeypatch.delenv("NEURO_INTERNAL_KEY", raising=False)

    def fake_get(url, timeout=5.0, headers=None):
        return _FakeResponse(403, text="Neuro access required")

    monkeypatch.setattr(cli.httpx, "get", fake_get)
    result = runner.invoke(cli.main, ["status"])

    assert "403" in result.output
    assert "Neuro access required" in result.output


def test_start_refuses_when_key_unset_in_production(runner, monkeypatch):
    """start() builds its own FastAPI app, bypassing api/__init__.py's
    startup check entirely -- so it must carry its own copy of the guard
    that refuses to expose an unauthenticated /learn and /audit."""
    monkeypatch.delenv("NEURO_INTERNAL_KEY", raising=False)
    monkeypatch.setattr(cli.settings, "ENVIRONMENT", "production", raising=False)

    called = {"uvicorn_run": False}
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: called.__setitem__("uvicorn_run", True))

    result = runner.invoke(cli.main, ["start"])

    assert result.exit_code != 0
    assert not called["uvicorn_run"], "server started despite an unset key in production"


def test_start_allows_when_key_is_set(runner, monkeypatch):
    monkeypatch.setenv("NEURO_INTERNAL_KEY", "the-shared-key")
    monkeypatch.setattr(cli.settings, "ENVIRONMENT", "production", raising=False)

    called = {"uvicorn_run": False}
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: called.__setitem__("uvicorn_run", True))

    result = runner.invoke(cli.main, ["start"])

    assert result.exit_code == 0
    assert called["uvicorn_run"]


def test_start_allows_outside_production_even_with_no_key(runner, monkeypatch):
    """Local dev must keep working with no key configured."""
    monkeypatch.delenv("NEURO_INTERNAL_KEY", raising=False)
    monkeypatch.setattr(cli.settings, "ENVIRONMENT", "development", raising=False)

    called = {"uvicorn_run": False}
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: called.__setitem__("uvicorn_run", True))

    result = runner.invoke(cli.main, ["start"])

    assert result.exit_code == 0
    assert called["uvicorn_run"]
