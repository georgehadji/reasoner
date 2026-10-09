"""Regression tests for the boot/deploy blockers re-landed from closed PR #9.

Docker is not available in CI, so the Dockerfile and docker-compose.yml
checks are static: they read the files and assert the properties whose
absence made a fresh deployment fail. The Python-side fixes (asyncpg DSN,
Alembic revision, build backend) are exercised directly.
"""

from __future__ import annotations

import importlib
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _compose() -> dict:
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(_read("docker-compose.yml"))


# ── Dockerfile ──────────────────────────────────────────────────────────────


def _copy_sources(dockerfile: str) -> list[str]:
    sources: list[str] = []
    for line in dockerfile.splitlines():
        parts = line.split()
        if parts and parts[0].upper() == "COPY" and "--from" not in line:
            sources.extend(p for p in parts[1:-1] if not p.startswith("--"))
    return sources


def test_dockerfile_copies_alembic_config_and_migrations():
    """docker-entrypoint.sh runs `alembic upgrade head` under `set -e`.

    Without alembic.ini and migrations/ in the image that command fails and
    the container exits before gunicorn starts.
    """
    assert "alembic upgrade head" in _read("docker-entrypoint.sh")
    sources = _copy_sources(_read("Dockerfile"))
    assert "alembic.ini" in sources
    assert any(s.rstrip("/") in ("migrations", "migrations/alembic") for s in sources)


def test_alembic_files_are_not_dockerignored():
    ignored = {
        line.strip().rstrip("/")
        for line in _read(".dockerignore").splitlines()
        if line.strip() and not line.startswith("#")
    }
    assert "alembic.ini" not in ignored
    assert "migrations" not in ignored


def test_healthcheck_scheme_follows_tls_configuration():
    """The entrypoint serves TLS when SSL_CERTFILE+SSL_KEYFILE are set, so a
    hardcoded http:// probe fails forever and the container is never healthy."""
    dockerfile = _read("Dockerfile")
    healthcheck = dockerfile[dockerfile.index("HEALTHCHECK") :]
    healthcheck = healthcheck[: healthcheck.index("ENTRYPOINT")]
    assert "SSL_CERTFILE" in healthcheck and "SSL_KEYFILE" in healthcheck
    assert "https" in healthcheck
    # Same condition the entrypoint uses to decide on TLS.
    entrypoint = _read("docker-entrypoint.sh")
    assert "SSL_CERTFILE" in entrypoint and "SSL_KEYFILE" in entrypoint


# ── docker-compose.yml ──────────────────────────────────────────────────────


def test_cert_generator_escapes_shell_variable_from_compose_interpolation():
    """Compose interpolates `$name` itself (to empty). The loop variable has to
    be written `$$service` to reach the shell, otherwise every cert is written
    to /certs/.key with CN= and the loop's files collide."""
    compose_text = _read("docker-compose.yml")
    block = compose_text[compose_text.index("cert-generator:") : compose_text.index("  caddy:")]
    bare = re.findall(r"(?<!\$)\$service\b", block)
    assert not bare, f"{len(bare)} unescaped $service reference(s) in cert-generator"
    assert "$$service" in block


def test_caddy_waits_for_backend_to_be_healthy():
    depends_on = _compose()["services"]["caddy"]["depends_on"]
    assert depends_on["backend"]["condition"] == "service_healthy"


# ── asyncpg DSN ─────────────────────────────────────────────────────────────


def test_asyncpg_dsn_strips_sqlalchemy_driver_suffix(monkeypatch):
    from reasoner.core.settings import Settings

    s = Settings()
    monkeypatch.setattr(
        s, "DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/reasoner?sslmode=require", raising=False
    )
    assert s.asyncpg_dsn == "postgresql://u:p@db:5432/reasoner?sslmode=require"


def test_asyncpg_dsn_leaves_plain_dsn_and_empty_unchanged(monkeypatch):
    from reasoner.core.settings import Settings

    s = Settings()
    monkeypatch.setattr(s, "DATABASE_URL", "postgresql://u:p@db/x", raising=False)
    assert s.asyncpg_dsn == "postgresql://u:p@db/x"
    monkeypatch.setattr(s, "DATABASE_URL", "", raising=False)
    assert s.asyncpg_dsn == ""


def test_lifespan_compaction_store_gets_asyncpg_safe_dsn():
    """asyncpg.create_pool rejects `postgresql+asyncpg://`; lifespan must not
    hand the raw settings.DATABASE_URL to PostgreSQLEventStore."""
    src = _read("src/reasoner/api/__init__.py")
    assert "PostgreSQLEventStore(settings.DATABASE_URL" not in src
    assert "PostgreSQLEventStore(settings.asyncpg_dsn" in src


# ── Alembic ─────────────────────────────────────────────────────────────────


def _script_directory():
    pytest.importorskip("alembic")
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations" / "alembic"))
    return ScriptDirectory.from_config(cfg)


def test_alembic_has_single_head_that_creates_account_deletion_log():
    script = _script_directory()
    heads = script.get_heads()
    assert len(heads) == 1, f"multiple alembic heads: {heads}"
    revisions = {rev.revision: rev for rev in script.walk_revisions()}
    creating = [
        rev
        for rev in revisions.values()
        if "account_deletion_log" in Path(rev.path).read_text(encoding="utf-8")
        and "CREATE TABLE IF NOT EXISTS account_deletion_log" in Path(rev.path).read_text(encoding="utf-8")
    ]
    assert creating, "no Alembic revision creates account_deletion_log"
    # Reachable from head, i.e. `alembic upgrade head` applies it.
    chain = {rev.revision for rev in script.walk_revisions(base="base", head=heads[0])}
    assert creating[0].revision in chain


def test_account_deletion_log_revision_matches_raw_sql_columns():
    raw = _read("migrations/005_account_deletion_log.sql")
    script = _script_directory()
    rev_src = next(
        Path(r.path).read_text(encoding="utf-8")
        for r in script.walk_revisions()
        if "account_deletion_log" in Path(r.path).read_text(encoding="utf-8")
    )
    for column in ("id UUID PRIMARY KEY", "user_id UUID NOT NULL", "deleted_at TIMESTAMPTZ NOT NULL", "ip_address TEXT", "user_agent TEXT"):
        assert column in raw and column in rev_src
    assert "idx_account_deletion_log_user" in rev_src
    assert "idx_account_deletion_log_deleted_at" in rev_src


# ── Build backend ───────────────────────────────────────────────────────────


def test_pyproject_build_backend_is_importable():
    backend = tomllib.loads(_read("pyproject.toml"))["build-system"]["build-backend"]
    assert backend == "setuptools.build_meta"
    # The CI image ships no setuptools; the value check above still runs there.
    pytest.importorskip("setuptools")
    module_name, _, attr = backend.partition(":")
    module = importlib.import_module(module_name)
    assert attr == "" or hasattr(module, attr)
