"""Credential leaks, incomplete erasure, unfiltered uploads, and a broken build.

Each of these looked fine and was not:
  - Request headers, including Authorization and session cookies, were written
    verbatim into the durable error store.
  - GDPR erasure skipped Neuro long-term memory — which holds prompts and
    responses in full — while still reporting "completed".
  - Uploaded document text reached prompts unsanitized, though scraped web
    content on the neighbouring path was filtered.
  - `pip install .` failed outright: the declared build backend does not exist.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from reasoner.core.logging_utils import redact_dict

REPO_ROOT = Path(__file__).resolve().parents[1]


class TestHeaderRedaction:
    @pytest.mark.parametrize(
        "header",
        ["authorization", "cookie", "x-admin-key", "x-api-key", "x-csrf-token"],
    )
    def test_credential_headers_are_redacted(self, header):
        out = redact_dict({header: "super-secret-value"})
        assert "super-secret-value" not in str(out), f"{header} leaked into the error store"

    def test_harmless_headers_survive(self):
        """Redaction has to leave enough behind to debug with."""
        out = redact_dict({"user-agent": "curl/8.0", "content-type": "application/json"})
        assert out["user-agent"] == "curl/8.0"
        assert out["content-type"] == "application/json"

    def test_error_handler_redacts_before_storing(self):
        src = (REPO_ROOT / "src" / "reasoner" / "api" / "error_handler.py").read_text(
            encoding="utf-8"
        )
        assert "redact_dict(dict(request.headers))" in src, (
            "raw headers reach the ErrorStore and the Sentry scope"
        )


class TestGdprErasureCoversLongTermMemory:
    def test_neuro_memory_is_actually_removed(self):
        src = (
            REPO_ROOT / "src" / "reasoner" / "application" / "services" / "data_eraser.py"
        ).read_text(encoding="utf-8")
        assert "get_agent_data_dir" in src and "rmtree" in src, (
            "erasure must remove the user's neuro agent directory; it previously "
            "imported SessionManager, never called it, and fell through"
        )

    def test_receipt_reports_neuro_status(self):
        src = (
            REPO_ROOT / "src" / "reasoner" / "application" / "services" / "data_eraser.py"
        ).read_text(encoding="utf-8")
        assert '"neuro_memory_erased"' in src

    def test_surviving_memory_downgrades_the_receipt(self):
        """A compliance receipt must not claim success over surviving data."""
        src = (
            REPO_ROOT / "src" / "reasoner" / "application" / "services" / "data_eraser.py"
        ).read_text(encoding="utf-8")
        assert "elif not neuro_erased:" in src

    def test_erasure_refuses_unexpected_paths(self):
        """A misconfigured data_dir must not turn erasure into a broad delete."""
        src = (
            REPO_ROOT / "src" / "reasoner" / "application" / "services" / "data_eraser.py"
        ).read_text(encoding="utf-8")
        assert "refusing to erase unexpected neuro path" in src


class TestUploadedContentIsSanitized:
    def test_both_attachment_paths_sanitize(self):
        """A document can carry 'ignore previous instructions' like any web page."""
        src = (REPO_ROOT / "src" / "reasoner" / "application" / "pipeline.py").read_text(
            encoding="utf-8"
        )
        assert "safe_chunk = sanitize_for_prompt(chunk_text)[0]" in src
        assert "safe_extracted = sanitize_for_prompt(extracted)[0]" in src

    def test_no_raw_extracted_text_reaches_the_prompt(self):
        src = (REPO_ROOT / "src" / "reasoner" / "application" / "pipeline.py").read_text(
            encoding="utf-8"
        )
        assert "{extracted}\\n" not in src, "raw extracted text still interpolated"


class TestPackageBuilds:
    def test_build_backend_exists(self):
        """`setuptools.backends._legacy:_Backend` is not a real module."""
        cfg = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        backend = cfg["build-system"]["build-backend"]
        assert backend == "setuptools.build_meta", f"unbuildable backend: {backend}"

    def test_package_discovery_is_explicit(self):
        """Auto-discovery is ambiguous with src/, tests/ and scripts/ present."""
        cfg = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        find = cfg["tool"]["setuptools"]["packages"]["find"]
        assert find["where"] == ["src"]


class TestRunRecordsAreNotCommitted:
    def test_history_is_gitignored(self):
        """docker-compose mounts ./history — it holds live user query text."""
        gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        lines = {line.strip() for line in gitignore.splitlines()}
        assert "history/" in lines, "root history/ must be ignored, not just src/reasoner/history/"


class TestUserFacingClaimsAreAccurate:
    def test_landing_page_does_not_promise_zero_hallucinations(self):
        """It contradicted the AI disclosure in Terms §3.

        Comments explain why the claim was removed, so only user-visible code is
        checked — otherwise the explanation trips the assertion it documents.
        """
        raw = (
            REPO_ROOT / "ui-next" / "src" / "components" / "landing" / "LandingPage.tsx"
        ).read_text(encoding="utf-8")
        rendered = "\n".join(
            line for line in raw.splitlines() if not line.strip().startswith("//")
        )
        assert "No hallucinations pass through" not in rendered

    @pytest.mark.parametrize("page", ["privacy", "terms", "cookies"])
    def test_legal_pages_do_not_fake_their_revision_date(self, page):
        """new Date() made every policy claim it was revised today, every day."""
        src = (REPO_ROOT / "ui-next" / "src" / "app" / page / "page.tsx").read_text(
            encoding="utf-8"
        )
        assert "new Date().toLocaleDateString" not in src


class TestCookieNoticeAndDataExport:
    def test_cookie_notice_is_mounted(self):
        layout = (REPO_ROOT / "ui-next" / "src" / "app" / "layout.tsx").read_text(
            encoding="utf-8"
        )
        assert "CookieNotice" in layout

    def test_cookie_notice_links_the_policy(self):
        src = (
            REPO_ROOT / "ui-next" / "src" / "components" / "layout" / "CookieNotice.tsx"
        ).read_text(encoding="utf-8")
        assert 'href="/cookies"' in src

    def test_data_export_is_reachable_from_settings(self):
        """Article 20 portability had a working endpoint and no way in."""
        page = (REPO_ROOT / "ui-next" / "src" / "app" / "settings" / "page.tsx").read_text(
            encoding="utf-8"
        )
        assert "exportAccountData" in page
        assert "Export My Data" in page
