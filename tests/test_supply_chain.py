"""Dependency provenance: reproducible builds and licence compliance.

requirements.lock existed but nothing installed from it, and it had drifted far
enough to still pin a version of asteval carrying a sandbox-escape advisory.
Separately, ~70 bundled packages shipped with no attribution file, and one of
them was AGPL — an obligation that lands squarely on a hosted service.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _lock_pins() -> dict[str, str]:
    pins = {}
    for line in (REPO_ROOT / "requirements.lock").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "==" not in line:
            continue
        name, _, version = line.partition("==")
        pins[name.split("[")[0].strip().lower()] = version.strip()
    return pins


class TestReproducibleBuilds:
    def test_dockerfile_installs_from_the_lockfile(self):
        """Ranged requirements mean two builds of one commit can differ."""
        dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
        assert "requirements.lock" in dockerfile
        assert re.search(r"pip install .*-r requirements\.lock", dockerfile), (
            "the image must install from the lock, not the ranged requirements.txt"
        )

    def test_lockfile_is_not_stale_on_security_pins(self):
        """The stale lock kept asteval at a version with a published advisory."""
        pins = _lock_pins()
        assert "asteval" in pins
        major, minor, *_ = pins["asteval"].split(".")
        assert (int(major), int(minor)) >= (1, 0), (
            f"asteval {pins['asteval']} is below the 1.0.6 security fix"
        )

    def test_observability_deps_are_locked(self):
        """Both were absent entirely, so /api/metrics returned an empty body."""
        pins = _lock_pins()
        assert "prometheus-client" in pins
        assert "sentry-sdk" in pins

    def test_lockfile_drift_is_checked_in_ci(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "security.yml").read_text(
            encoding="utf-8"
        )
        assert "requirements.lock is current" in workflow


class TestLicenceCompliance:
    def test_notice_exists(self):
        assert (REPO_ROOT / "NOTICE.md").exists(), (
            "MIT, BSD and Apache-2.0 all require their notices to be reproduced "
            "in distributions; the containers ship ~100 such packages"
        )

    def test_notice_lists_both_ecosystems(self):
        notice = (REPO_ROOT / "NOTICE.md").read_text(encoding="utf-8")
        assert "## Python" in notice
        assert "## JavaScript" in notice

    def test_agpl_dependency_is_not_shipped_by_default(self):
        """pymupdf is AGPL-3.0/commercial.

        AGPL section 13 obliges you to offer source to users interacting over a
        network, which is precisely a hosted SaaS — so shipping it by default
        put that obligation on every deployment of an MIT-licensed project.
        It is used only for optional scanned-PDF OCR; pypdf (BSD) handles normal
        text extraction.
        """
        pins = _lock_pins()
        assert "pymupdf" not in pins, (
            "pymupdf is AGPL — it must be an explicit opt-in, not a default install"
        )

    def test_pymupdf_absence_degrades_gracefully(self):
        """Removing it must not break uploads, only the OCR path."""
        src = (REPO_ROOT / "src" / "reasoner" / "infrastructure" / "uploader.py").read_text(
            encoding="utf-8"
        )
        assert "except ImportError:" in src
        assert "install pymupdf" in src

    def test_requirements_explains_the_licence_decision(self):
        """A future maintainer will otherwise 'fix' the missing dependency."""
        reqs = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
        assert "AGPL" in reqs and "pymupdf" in reqs

    @pytest.mark.parametrize("ecosystem", ["Python", "JavaScript"])
    def test_notice_is_not_empty(self, ecosystem):
        notice = (REPO_ROOT / "NOTICE.md").read_text(encoding="utf-8")
        section = notice.split(f"## {ecosystem}")[1]
        rows = [ln for ln in section.splitlines() if ln.startswith("| ") and "---" not in ln]
        assert len(rows) > 5, f"{ecosystem} attribution table looks empty"
