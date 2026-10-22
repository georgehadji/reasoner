"""scripts/migrate_history_layout.py moves flat history files into owner directories (PER-12).

Dry run by default; --apply writes; idempotent; writes the marker last, so a
crash half way leaves the repository reading the flat layout as well.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from reasoner.infrastructure.persistence.history_files import LAYOUT_MARKER, owner_key

pytestmark = pytest.mark.unit

SCRIPT = Path(__file__).parent.parent / "scripts" / "migrate_history_layout.py"


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("migrate_history_layout", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _flat(root: Path, entry_id: str, owner: str | None) -> None:
    (root / f"{entry_id}.json").write_text(
        json.dumps({"id": entry_id, "user_id": owner}), encoding="utf-8"
    )


def test_dry_run_changes_nothing(script, tmp_path):
    _flat(tmp_path, "e1", "user-a")

    moved = script.migrate(tmp_path, apply=False)

    assert moved == {"moved": 1, "skipped": 0}
    assert (tmp_path / "e1.json").exists()
    assert not (tmp_path / LAYOUT_MARKER).exists()


def test_apply_moves_each_file_into_its_owner_directory(script, tmp_path):
    _flat(tmp_path, "e1", "user-a")
    _flat(tmp_path, "e2", "user-b")
    _flat(tmp_path, "e3", None)

    script.migrate(tmp_path, apply=True)

    assert (tmp_path / owner_key("user-a") / "e1.json").exists()
    assert (tmp_path / owner_key("user-b") / "e2.json").exists()
    assert (tmp_path / "anon" / "e3.json").exists()
    assert not list(tmp_path.glob("*.json"))
    assert (tmp_path / LAYOUT_MARKER).exists()


def test_apply_is_idempotent(script, tmp_path):
    _flat(tmp_path, "e1", "user-a")
    script.migrate(tmp_path, apply=True)

    again = script.migrate(tmp_path, apply=True)

    assert again == {"moved": 0, "skipped": 0}
    assert (tmp_path / owner_key("user-a") / "e1.json").exists()


def test_an_unreadable_file_is_left_in_place_and_blocks_the_marker(script, tmp_path):
    _flat(tmp_path, "e1", "user-a")
    (tmp_path / "torn.json").write_text("{not json", encoding="utf-8")

    result = script.migrate(tmp_path, apply=True)

    assert result == {"moved": 1, "skipped": 1}
    assert (tmp_path / "torn.json").exists()
    assert not (tmp_path / LAYOUT_MARKER).exists(), "unattributed data keeps the flat reads on"


def test_an_existing_file_in_the_target_is_not_overwritten(script, tmp_path):
    _flat(tmp_path, "e1", "user-a")
    target = tmp_path / owner_key("user-a")
    target.mkdir()
    (target / "e1.json").write_text('{"id": "e1", "newer": true}', encoding="utf-8")

    script.migrate(tmp_path, apply=True)

    assert json.loads((target / "e1.json").read_text(encoding="utf-8")).get("newer") is True
    assert not (tmp_path / "e1.json").exists(), "the flat duplicate is dropped"
