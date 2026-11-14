"""/changelog says every entry names the commit on main it shipped in.

ui-next/src/lib/changelog.ts is hand-written, so a mistyped hash, or one
from a branch that never merged, would ship silently. This checks each
hash resolves to a commit and, where origin/main is fetched, that main
contains it.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHANGELOG = ROOT / "ui-next" / "src" / "lib" / "changelog.ts"


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)


def _commits() -> list[str]:
    return re.findall(r"commit:\s*'([0-9a-f]{7,40})'", CHANGELOG.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def full_history() -> None:
    if shutil.which("git") is None or _git("rev-parse", "--git-dir").returncode != 0:
        pytest.skip("not a git checkout")
    if _git("rev-parse", "--is-shallow-repository").stdout.strip() == "true":
        pytest.skip("shallow clone: older commits are absent (needs fetch-depth: 0)")


def test_every_entry_names_a_commit():
    text = CHANGELOG.read_text(encoding="utf-8")
    dates = re.findall(r"date:\s*'\d{4}-\d{2}-\d{2}'", text)
    assert dates, "the changelog page renders its latest entry; the list must not be empty"
    assert len(_commits()) == len(dates), "an entry is missing its commit"


@pytest.mark.parametrize("commit", _commits())
def test_commit_exists(full_history, commit):
    exists = _git("cat-file", "-e", f"{commit}^{{commit}}").returncode == 0
    assert exists, f"{commit} is not a commit here"


@pytest.mark.parametrize("commit", _commits())
def test_commit_is_on_main(full_history, commit):
    if _git("rev-parse", "--verify", "--quiet", "origin/main").returncode != 0:
        pytest.skip("origin/main not fetched")
    on_main = _git("merge-base", "--is-ancestor", commit, "origin/main").returncode == 0
    assert on_main, f"{commit} is not on main: unmerged work has not shipped"
