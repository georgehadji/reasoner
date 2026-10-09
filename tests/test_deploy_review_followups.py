"""Regression tests for the review follow-ups on the boot/deploy PR.

Docker is not available in CI, so the container-level behaviour is reproduced
with plain openssl + Python: the compose cert-generator script is executed
for real (shell, minus apk/chown), and the Dockerfile HEALTHCHECK one-liner is
extracted from the Dockerfile and run against a local TLS server.
"""

from __future__ import annotations

import ast
import http.server
import os
import re
import shutil
import ssl
import subprocess
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

needs_openssl = pytest.mark.skipif(
    shutil.which("openssl") is None or shutil.which("sh") is None,
    reason="needs openssl and sh on PATH",
)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _cert_script() -> str:
    yaml = pytest.importorskip("yaml")
    compose = yaml.safe_load(_read("docker-compose.yml"))
    command = compose["services"]["cert-generator"]["command"]
    assert command[:2] == ["sh", "-c"]
    return command[2]


def _healthcheck_code() -> str:
    """The python source of the Dockerfile HEALTHCHECK `python -c "..."`."""
    match = re.search(r'HEALTHCHECK[^\n]*\\\n\s*CMD python -c "(.*)" \|\| exit 1', _read("Dockerfile"))
    assert match, "could not find the HEALTHCHECK python -c one-liner"
    return match.group(1)


# ── HEALTHCHECK ─────────────────────────────────────────────────────────────


def test_healthcheck_one_liner_compiles_and_clears_strict_flag():
    code = _healthcheck_code()
    compile(code, "<healthcheck>", "exec")
    assert "VERIFY_X509_STRICT" in code
    assert "https" in code and "SSL_CERTFILE" in code and "SSL_KEYFILE" in code


def test_healthcheck_start_period_covers_migrations_and_worker_boot():
    match = re.search(r"--start-period=(\d+)s", _read("Dockerfile"))
    assert match and int(match.group(1)) >= 60


# ── cert-generator + healthcheck against a real TLS server ──────────────────


def _run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, env={**os.environ, "MSYS_NO_PATHCONV": "1"})


def _generate_with_compose_script(certs: Path) -> None:
    """Run the real cert-generator script against `certs` (no apk, no chown)."""
    script = _cert_script().replace("$$", "$").replace("/certs", certs.as_posix())
    script = "\n".join(
        line for line in script.splitlines() if not line.startswith(("apk ", "chown ")) and "chown" not in line.split("#")[0]
    )
    result = subprocess.run(
        ["sh", "-c", script], capture_output=True, text=True, env={**os.environ, "MSYS_NO_PATHCONV": "1"}
    )
    assert result.returncode == 0, result.stderr


def _generate_old_ca_and_backend_cert(certs: Path) -> None:
    """A volume created before the fix: stock `openssl req -x509`, no keyUsage."""
    certs.mkdir(parents=True, exist_ok=True)
    _run(["openssl", "genrsa", "-out", "ca.key", "2048"], certs)
    _run(["openssl", "req", "-x509", "-new", "-nodes", "-key", "ca.key", "-sha256", "-days", "30",
          "-out", "ca.crt", "-subj", "/CN=Internal CA"], certs)
    _run(["openssl", "genrsa", "-out", "backend.key", "2048"], certs)
    _run(["openssl", "req", "-new", "-key", "backend.key", "-out", "backend.csr", "-subj", "/CN=backend"], certs)
    (certs / "backend.ext").write_text("subjectAltName = DNS:backend, DNS:localhost\n")
    _run(["openssl", "x509", "-req", "-in", "backend.csr", "-CA", "ca.crt", "-CAkey", "ca.key",
          "-CAcreateserial", "-out", "backend.crt", "-days", "30", "-sha256", "-extfile", "backend.ext"], certs)


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):  # silence
        pass


@pytest.fixture
def tls_server():
    servers: list[http.server.HTTPServer] = []

    def start(certs: Path) -> int:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certs / "backend.crt", certs / "backend.key")
        srv = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
        return srv.server_address[1]

    yield start
    for srv in servers:
        srv.shutdown()
        srv.server_close()


def _strict_client_context(ca: Path) -> ssl.SSLContext:
    """What python:3.13+ create_default_context() returns."""
    ctx = ssl.create_default_context(cafile=str(ca))
    ctx.verify_flags |= ssl.VERIFY_X509_STRICT
    return ctx


def _fetch(port: int, ctx: ssl.SSLContext) -> int:
    return urllib.request.urlopen(f"https://localhost:{port}/", context=ctx, timeout=10).status


def _run_healthcheck(monkeypatch, port: int, ca: Path) -> None:
    """Execute the Dockerfile one-liner with python>=3.13 semantics (strict on)."""
    real = ssl.create_default_context

    def strict_default(*args, **kwargs):
        ctx = real(*args, **kwargs)
        ctx.verify_flags |= ssl.VERIFY_X509_STRICT
        return ctx

    code = (
        _healthcheck_code()
        .replace("/certs/ca.crt", ca.as_posix())
        .replace("localhost:8000", f"localhost:{port}")
    )
    monkeypatch.setattr(ssl, "create_default_context", strict_default)
    monkeypatch.setenv("SSL_CERTFILE", "x")
    monkeypatch.setenv("SSL_KEYFILE", "y")
    exec(compile(code, "<healthcheck>", "exec"), {})  # noqa: S102


@needs_openssl
def test_strict_verification_rejects_old_ca_but_healthcheck_passes(tmp_path, tls_server, monkeypatch):
    """The reported defect: python 3.13+ strict verification vs a CA with no keyUsage."""
    _generate_old_ca_and_backend_cert(tmp_path)
    port = tls_server(tmp_path)

    # Repro: plain strict verification (what the unfixed healthcheck did) fails...
    with pytest.raises(urllib.error.URLError, match="key usage"):
        _fetch(port, _strict_client_context(tmp_path / "ca.crt"))

    # ...the fixed one-liner, under the same strict default, succeeds.
    _run_healthcheck(monkeypatch, port, tmp_path / "ca.crt")


@needs_openssl
def test_healthcheck_still_verifies_hostname_and_chain(tmp_path, tls_server, monkeypatch):
    """Clearing STRICT must not disable verification: a foreign CA is rejected."""
    _generate_old_ca_and_backend_cert(tmp_path)
    port = tls_server(tmp_path)
    other = tmp_path / "other"
    _generate_old_ca_and_backend_cert(other)

    with pytest.raises(urllib.error.URLError):
        _run_healthcheck(monkeypatch, port, other / "ca.crt")


@needs_openssl
def test_compose_generated_ca_passes_strict_verification(tmp_path, tls_server):
    """New volumes: the CA has keyUsage, so even strict verification succeeds."""
    _generate_with_compose_script(tmp_path)
    port = tls_server(tmp_path)
    assert _fetch(port, _strict_client_context(tmp_path / "ca.crt")) == 200


@needs_openssl
def test_each_service_cert_carries_only_its_own_san(tmp_path):
    _generate_with_compose_script(tmp_path)
    for service in ("backend", "frontend", "postgres", "valkey"):
        text = subprocess.run(
            ["openssl", "x509", "-in", str(tmp_path / f"{service}.crt"), "-noout", "-ext", "subjectAltName"],
            capture_output=True, text=True, check=True,
        ).stdout
        assert f"DNS:{service}" in text and "DNS:localhost" in text
        for other in {"backend", "frontend", "postgres", "valkey"} - {service}:
            assert f"DNS:{other}" not in text, f"{service}.crt carries {other}'s SAN"


@needs_openssl
def test_cert_generator_recovers_when_ca_key_exists_but_ca_crt_is_missing(tmp_path):
    """A run that died between `genrsa` and `req -x509` leaves ca.key alone.

    Guarding on ca.key only would skip CA creation on every later run and then
    fail signing for good; the CA must be rebuilt when either file is missing.
    """
    _run(["openssl", "genrsa", "-out", "ca.key", "2048"], tmp_path)
    assert not (tmp_path / "ca.crt").exists()

    _generate_with_compose_script(tmp_path)

    assert (tmp_path / "ca.crt").exists()
    for service in ("backend", "frontend", "postgres", "valkey"):
        assert (tmp_path / f"{service}.crt").exists()


@needs_openssl
def test_cert_generator_is_rerunnable_and_keeps_an_existing_ca(tmp_path):
    """A second run on an existing volume succeeds and reuses the CA."""
    _generate_with_compose_script(tmp_path)
    ca_before = (tmp_path / "ca.crt").read_bytes()

    _generate_with_compose_script(tmp_path)

    assert (tmp_path / "ca.crt").read_bytes() == ca_before


# ── key ownership ───────────────────────────────────────────────────────────


def test_backend_key_is_chowned_to_the_uid_pinned_in_the_dockerfile():
    dockerfile = _read("Dockerfile")
    uid = re.search(r"useradd -r -u (\d+) ", dockerfile)
    gid = re.search(r"groupadd -r -g (\d+) appuser", dockerfile)
    assert uid and gid, "appuser uid/gid must be pinned so the key chown can match"
    script = _cert_script()
    assert f"chown {uid.group(1)}:{gid.group(1)} /certs/backend.key" in script
    # postgres:16-alpine runs as uid 70 and rejects a key it does not own.
    assert "postgres:16-alpine" in _read("docker-compose.yml")
    assert "chown 70:70 /certs/postgres.key" in script


# ── Alembic env: sslmode ────────────────────────────────────────────────────


def _split_sslmode():
    """env.py runs the migration at import, so lift the helper out with ast."""
    pytest.importorskip("sqlalchemy")
    from sqlalchemy.engine.url import make_url

    tree = ast.parse(_read("migrations/alembic/env.py"))
    func = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "split_sslmode")
    namespace = {"make_url": make_url}
    exec(compile(ast.Module([func], type_ignores=[]), "env.py", "exec"), namespace)  # noqa: S102
    return namespace["split_sslmode"]


def test_split_sslmode_moves_param_to_asyncpg_ssl_connect_arg():
    split = _split_sslmode()
    url, args = split("postgresql+asyncpg://postgres:p%40ss@postgres:5432/reasoner?sslmode=require")
    assert args == {"ssl": "require"}
    assert "sslmode" not in url
    assert url == "postgresql+asyncpg://postgres:p%40ss@postgres:5432/reasoner"


def test_split_sslmode_keeps_other_query_params():
    split = _split_sslmode()
    url, args = split("postgresql+asyncpg://u:p@h/db?sslmode=verify-full&application_name=x")
    assert args == {"ssl": "verify-full"}
    assert "application_name=x" in url and "sslmode" not in url


def test_split_sslmode_is_a_noop_without_sslmode_or_for_other_drivers():
    split = _split_sslmode()
    plain = "postgresql+asyncpg://u:p@h/db"
    assert split(plain) == (plain, {})
    psycopg = "postgresql+psycopg2://u:p@h/db?sslmode=require"
    assert split(psycopg) == (psycopg, {})


def test_asyncpg_dialect_no_longer_forwards_sslmode_kwarg():
    """The reported TypeError: the dialect turned ?sslmode= into connect(sslmode=)."""
    pytest.importorskip("asyncpg")
    from sqlalchemy.dialects.postgresql.asyncpg import PGDialect_asyncpg
    from sqlalchemy.engine.url import make_url

    raw = "postgresql+asyncpg://u:p@db:5432/r?sslmode=require"
    _, kwargs = PGDialect_asyncpg().create_connect_args(make_url(raw))
    assert "sslmode" in kwargs  # why asyncpg.connect() raised TypeError

    url, connect_args = _split_sslmode()(raw)
    _, kwargs = PGDialect_asyncpg().create_connect_args(make_url(url))
    assert "sslmode" not in kwargs and connect_args == {"ssl": "require"}


def test_asyncpg_accepts_sslmode_in_a_dsn_natively():
    """The app's own pools (settings.asyncpg_dsn, `.replace("+asyncpg", "")`) are fine."""
    pytest.importorskip("asyncpg")
    from asyncpg import connect_utils

    _, params = connect_utils._parse_connect_dsn_and_args(
        dsn="postgresql://u:p@db:5432/r?sslmode=require",
        host=None, port=None, user=None, password=None, passfile=None, database=None,
        ssl=None, direct_tls=None, server_settings=None, target_session_attrs=None,
        krbsrvname=None, gsslib=None, service=None, servicefile=None,
    )
    assert isinstance(params.ssl, ssl.SSLContext)


# ── Alembic revision downgrade ──────────────────────────────────────────────


def test_account_deletion_log_downgrade_does_not_drop_the_audit_table():
    pytest.importorskip("alembic")
    import importlib.util

    path = ROOT / "migrations" / "alembic" / "versions" / "20260929_000000_add_account_deletion_log.py"
    spec = importlib.util.spec_from_file_location("rev_20260929", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Outside a migration context any `op.*` call raises, so a downgrade that
    # still issued DROP TABLE would fail here; a no-op returns cleanly.
    assert module.downgrade() is None
    tree = ast.parse(path.read_text(encoding="utf-8"))
    downgrade = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "downgrade")
    calls = [n for n in ast.walk(downgrade) if isinstance(n, ast.Call)]
    assert not calls, "downgrade must not issue any operation"
