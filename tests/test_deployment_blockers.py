"""Regressions for bugs that made the documented production deploy impossible.

`docker compose up -d --build` — the deploy command in DEPLOY.md — could not
produce a working stack. Each test below pins one of the causes.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest

from reasoner.core.logging_utils import install_global_redaction, redact_sensitive
from reasoner.core.settings import Settings, settings

REPO_ROOT = Path(__file__).resolve().parents[1]


class TestAsyncpgDsn:
    """asyncpg rejects SQLAlchemy's `postgresql+asyncpg://` scheme outright.

    Patch Settings (the class) and read through `settings` (the instance):
    monkeypatch.undo() restores by setattr, so patching the instance would leave
    a permanent shadowing attribute behind for the rest of the test session.
    """

    def test_driver_suffix_is_stripped(self, monkeypatch):
        monkeypatch.setattr(
            Settings, "DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/db?sslmode=require"
        )
        assert settings.ASYNCPG_DSN == "postgresql://u:p@h:5432/db?sslmode=require"

    def test_plain_dsn_is_untouched(self, monkeypatch):
        monkeypatch.setattr(Settings, "DATABASE_URL", "postgresql://u:p@h:5432/db")
        assert settings.ASYNCPG_DSN == "postgresql://u:p@h:5432/db"

    def test_empty_dsn_stays_empty(self, monkeypatch):
        monkeypatch.setattr(Settings, "DATABASE_URL", "")
        assert settings.ASYNCPG_DSN == ""

    async def test_asyncpg_accepts_the_normalized_dsn(self, monkeypatch):
        """The scheme must survive asyncpg's own DSN parser.

        The raw value raises ClientConfigurationError before any connection is
        attempted; the normalized one must get far enough to fail on the network
        instead, which is all we can reach without a live database.
        """
        asyncpg = pytest.importorskip("asyncpg")
        monkeypatch.setattr(
            Settings, "DATABASE_URL",
            "postgresql+asyncpg://u:p@127.0.0.1:1/db",
        )
        with pytest.raises(Exception) as excinfo:
            await asyncpg.create_pool(settings.ASYNCPG_DSN, timeout=1)
        assert not isinstance(excinfo.value, asyncpg.exceptions.ClientConfigurationError), (
            f"asyncpg still rejects the DSN: {excinfo.value}"
        )


class TestDockerImageContents:
    """docker-entrypoint.sh runs `alembic upgrade head` under `set -e`."""

    def test_dockerfile_copies_alembic_config(self):
        dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
        assert re.search(r"^COPY\s+alembic\.ini", dockerfile, re.MULTILINE), (
            "alembic.ini is missing from the image — `alembic upgrade head` exits 1 "
            "with 'No config file' and set -e kills the container on first boot"
        )

    def test_dockerfile_copies_migrations(self):
        dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
        assert re.search(r"^COPY\s+migrations/", dockerfile, re.MULTILINE), (
            "migrations/ is missing from the image — there are no revisions to apply"
        )

    def test_healthcheck_is_not_hardcoded_to_http(self):
        """compose sets SSL_CERTFILE, so port 8000 serves TLS."""
        dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
        healthcheck = dockerfile[dockerfile.index("HEALTHCHECK"):]
        assert "SSL_CERTFILE" in healthcheck, (
            "healthcheck must pick its scheme from SSL_CERTFILE; a fixed http:// "
            "probe fails forever once gunicorn is given --certfile"
        )


class TestComposeCertGeneration:
    """Compose consumes `$VAR` before the shell sees it; `$$` escapes it."""

    def test_cert_loop_variable_is_escaped(self):
        compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        cert_block = compose[compose.index("cert-generator:"):compose.index("caddy:")]
        assert "$$service" in cert_block
        assert not re.search(r"(?<!\$)\$service", cert_block), (
            "unescaped $service is interpolated to empty by Compose, so the loop "
            "writes /certs/.key and every service depending on certs fails to start"
        )


class TestAccountDeletionLogMigration:
    """saas_router INSERTs into a table only a never-run .sql file created."""

    def test_alembic_revision_creates_the_table(self):
        versions = REPO_ROOT / "migrations" / "alembic" / "versions"
        sources = [p.read_text(encoding="utf-8") for p in versions.glob("*.py")]
        assert any("account_deletion_log" in s for s in sources), (
            "no Alembic revision creates account_deletion_log, so GDPR account "
            "deletion fails against an Alembic-provisioned database"
        )

    def test_revision_chain_is_linear(self):
        """A second head would make `alembic upgrade head` ambiguous and fail."""
        versions = REPO_ROOT / "migrations" / "alembic" / "versions"
        revisions, downs = set(), set()
        for path in versions.glob("*.py"):
            src = path.read_text(encoding="utf-8")
            rev = re.search(r'^revision:\s*str\s*=\s*"([^"]+)"', src, re.MULTILINE)
            down = re.search(r'^down_revision:.*?=\s*"([^"]+)"', src, re.MULTILINE)
            if rev:
                revisions.add(rev.group(1))
            if down:
                downs.add(down.group(1))
        heads = revisions - downs
        assert len(heads) == 1, f"expected exactly one Alembic head, found {heads}"


class TestSecretRedaction:
    """Redaction was installed where it could not see ordinary log records."""

    @pytest.mark.parametrize(
        "secret",
        [
            "sk-or-v1-4f8a2b9c1d3e5f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f",
            "sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
            "sk-ant-api03-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789AbCdEf",
        ],
    )
    def test_provider_keys_are_redacted(self, secret):
        """Hyphenated key bodies used to defeat the [a-zA-Z0-9]{20,} class."""
        assert secret not in redact_sensitive(f"calling with {secret}")

    def test_postgresql_dsn_password_is_redacted(self):
        """`postgres://` alone never matched the `postgresql://` scheme in use."""
        out = redact_sensitive("db=postgresql+asyncpg://postgres:hunter2@host:5432/db")
        assert "hunter2" not in out

    def test_child_logger_output_is_redacted(self, caplog):
        """Every module uses getLogger(__name__); a root-logger filter misses those."""
        install_global_redaction()
        secret = "sk-or-v1-4f8a2b9c1d3e5f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f"
        with caplog.at_level(logging.ERROR):
            logging.getLogger("reasoner.some.child.module").error("key=%s", secret)
        assert secret not in caplog.text

    def test_redaction_install_is_idempotent(self):
        """Repeated imports must not stack record factories."""
        install_global_redaction()
        first = logging.getLogRecordFactory()
        install_global_redaction()
        assert logging.getLogRecordFactory() is first

    def test_secret_passed_as_arg_is_redacted(self):
        """The realistic shape: the whole secret arrives as one argument."""
        install_global_redaction()
        factory = logging.getLogRecordFactory()
        secret = "sk-proj-" + "A" * 40
        record = factory("n", logging.ERROR, "p", 1, "key=%s", (secret,), None)
        assert secret not in record.getMessage()

    def test_redaction_runs_before_interpolation(self):
        """Known limitation, pinned so a future change is a deliberate one.

        Records are redacted at creation, so a secret split across the format
        string and its arguments ("sk-proj-%s" % body) is not reassembled and
        therefore not matched. Callers must log a secret as a whole value, which
        is what every call site in this codebase does.
        """
        install_global_redaction()
        factory = logging.getLogRecordFactory()
        record = factory("n", logging.ERROR, "p", 1, "sk-proj-%s", ("A" * 40,), None)
        assert "sk-proj-" + "A" * 40 in record.getMessage()
