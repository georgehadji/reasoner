"""PER-12: history is partitioned by owner, read off the event loop, and bounded.

`GET /api/history` read and parsed every user's file synchronously on the
event loop, `/api/history/tagged` took the last N entries across all users
before filtering by user, and nothing pruned the files. Behaviour under test:
`FileHistoryRepository` (infrastructure/persistence/history_files.py), the
adapter of the `HistoryRepository` port.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from reasoner.infrastructure.persistence.history_files import (
    LAYOUT_MARKER,
    FileHistoryRepository,
    owner_key,
)

pytestmark = pytest.mark.unit

A, B = "user-a", "user-b"


def _entry(entry_id: str, owner: str | None, ts: str, method="debate", preset="debate-budget"):
    return {
        "id": entry_id, "user_id": owner, "problem": "p", "preset": preset,
        "method": method, "timestamp": ts, "tokens": {"total": 1}, "status": "completed",
    }


@pytest.fixture
def repo(tmp_path) -> FileHistoryRepository:
    return FileHistoryRepository(tmp_path, max_entries=500)


def test_owner_key_is_a_stable_digest_never_the_raw_id():
    assert owner_key(A) == owner_key(A) != owner_key(B)
    assert owner_key(A).startswith("u-") and A not in owner_key(A)
    assert owner_key(None) == owner_key("") == "anon"


@pytest.mark.asyncio
async def test_save_then_get_round_trips_and_leaves_no_temp_file(repo, tmp_path):
    await repo.save(_entry("e1", A, "2026-10-01T00:00:00"))

    assert (await repo.get(A, "e1"))["id"] == "e1"
    assert [p.name for p in (tmp_path / owner_key(A)).iterdir()] == ["e1.json"]


@pytest.mark.asyncio
async def test_listing_for_one_owner_opens_none_of_anothers_files(repo, tmp_path, monkeypatch):
    for i in range(5):
        await repo.save(_entry(f"a{i}", A, f"2026-10-0{i + 1}T00:00:00"))
        await repo.save(_entry(f"b{i}", B, f"2026-10-0{i + 1}T00:00:00"))
    opened: list[Path] = []
    real = Path.read_text

    def spy(self, *a, **k):
        opened.append(self)
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", spy)
    entries, total = await repo.list(A, limit=50, offset=0)

    assert total == 5 and len(entries) == 5
    assert opened, "the spy must see A's reads"
    assert all(tmp_path / owner_key(A) in p.parents for p in opened)


@pytest.mark.asyncio
async def test_a_page_parses_only_the_requested_entries(repo, monkeypatch):
    for i in range(20):
        await repo.save(_entry(f"a{i:02d}", A, f"2026-10-01T00:00:{i:02d}"))
    opened: list[Path] = []
    real = Path.read_text

    def spy(self, *a, **k):
        opened.append(self)
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", spy)

    entries, total = await repo.list(A, limit=3, offset=0)

    assert total == 20 and len(entries) == 3
    assert len(opened) == 3


@pytest.mark.asyncio
async def test_newest_first(repo):
    for i in range(3):
        await repo.save(_entry(f"a{i}", A, f"2026-10-0{i + 1}T00:00:00"))
    entries, _ = await repo.list(A, limit=10, offset=0)
    assert [e["id"] for e in entries] == ["a2", "a1", "a0"]


@pytest.mark.asyncio
async def test_tagged_returns_my_entries_even_when_others_have_newer_ones(repo):
    await repo.save(_entry("mine", A, "2026-10-01T00:00:00", method="debate"))
    for i in range(30):
        await repo.save(_entry(f"b{i}", B, f"2026-10-02T00:00:{i:02d}", method="debate"))

    entries, _ = await repo.list(A, limit=5, offset=0, tag="method_debate")

    assert [e["id"] for e in entries] == ["mine"]


@pytest.mark.asyncio
async def test_the_tag_filter_runs_before_the_limit(repo):
    await repo.save(_entry("old-debate", A, "2026-10-01T00:00:00", method="debate"))
    for i in range(5):
        await repo.save(_entry(f"jury{i}", A, f"2026-10-02T00:00:0{i}", method="jury"))

    entries, _ = await repo.list(A, limit=2, offset=0, tag="method_debate")

    assert [e["id"] for e in entries] == ["old-debate"]


@pytest.mark.asyncio
async def test_listing_does_not_block_the_loop_with_many_other_files(repo, tmp_path):
    await repo.save(_entry("mine", A, "2026-10-01T00:00:00"))
    other = tmp_path / owner_key(B)
    other.mkdir()
    for i in range(10_000):
        (other / f"b{i}.json").write_text("{}", encoding="utf-8")

    entries, _ = await asyncio.wait_for(repo.list(A, limit=50, offset=0), timeout=0.05)

    assert [e["id"] for e in entries] == ["mine"]


@pytest.mark.asyncio
async def test_a_loop_keeps_ticking_while_a_listing_runs(repo):
    for i in range(300):
        await repo.save(_entry(f"a{i}", A, f"2026-10-01T00:{i // 60:02d}:{i % 60:02d}"))
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0)
            ticks += 1

    task = asyncio.create_task(ticker())
    await repo.list(A, limit=300, offset=0, tag="method_debate")
    task.cancel()

    assert ticks > 0


@pytest.mark.asyncio
async def test_each_owner_keeps_only_the_newest_entries(tmp_path):
    repo = FileHistoryRepository(tmp_path, max_entries=3)
    for i in range(6):
        await repo.save(_entry(f"a{i}", A, f"2026-10-0{i + 1}T00:00:00"))
        await repo.save(_entry(f"b{i}", B, f"2026-10-0{i + 1}T00:00:00"))

    a, total = await repo.list(A, limit=50, offset=0)

    assert total == 3
    assert {e["id"] for e in a} == {"a3", "a4", "a5"}
    assert (await repo.list(B, limit=50, offset=0))[1] == 3, "pruning is per owner"


@pytest.mark.asyncio
async def test_another_owners_entry_is_not_readable_or_deletable(repo):
    await repo.save(_entry("e1", A, "2026-10-01T00:00:00"))

    assert await repo.get(B, "e1") is None
    assert await repo.delete(B, "e1") is False
    assert await repo.get(A, "e1") is not None


@pytest.mark.asyncio
async def test_an_anonymous_entry_is_not_any_users(repo):
    await repo.save(_entry("anon1", None, "2026-10-01T00:00:00"))

    assert await repo.get(A, "anon1") is None
    assert (await repo.list(A, limit=50, offset=0))[1] == 0


@pytest.mark.asyncio
async def test_an_id_cannot_walk_out_of_the_owner_directory(repo, tmp_path):
    outside = tmp_path.parent / "outside.json"
    outside.write_text(json.dumps(_entry("outside", A, "t")), encoding="utf-8")
    try:
        assert await repo.get(A, "../outside") is None
        assert await repo.delete(A, "../outside") is False
    finally:
        outside.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_erase_removes_one_owner_and_counts_it(repo, tmp_path):
    for i in range(3):
        await repo.save(_entry(f"a{i}", A, f"2026-10-0{i + 1}T00:00:00"))
    await repo.save(_entry("b0", B, "2026-10-01T00:00:00"))

    assert await repo.erase(A) == (3, 0)

    assert not (tmp_path / owner_key(A)).exists()
    assert (await repo.list(B, limit=50, offset=0))[1] == 1


@pytest.mark.asyncio
async def test_erase_removes_an_unreadable_file_in_the_owners_directory(repo, tmp_path):
    await repo.save(_entry("a0", A, "2026-10-01T00:00:00"))
    (tmp_path / owner_key(A) / "torn.json").write_text("{not json", encoding="utf-8")

    assert await repo.erase(A) == (2, 0), "ownership comes from the directory, not the content"


# ── flat layout, until the migration marker exists ───────────────────────


def _flat(tmp_path: Path, entry: dict) -> None:
    (tmp_path / f"{entry['id']}.json").write_text(json.dumps(entry), encoding="utf-8")


@pytest.mark.asyncio
async def test_flat_files_stay_readable_until_the_migration_is_done(repo, tmp_path):
    _flat(tmp_path, _entry("old-a", A, "2026-09-01T00:00:00"))
    _flat(tmp_path, _entry("old-b", B, "2026-09-02T00:00:00"))
    await repo.save(_entry("new-a", A, "2026-10-01T00:00:00"))

    entries, total = await repo.list(A, limit=50, offset=0)

    assert [e["id"] for e in entries] == ["new-a", "old-a"] and total == 2
    assert (await repo.get(A, "old-a")) is not None
    assert (await repo.get(A, "old-b")) is None


@pytest.mark.asyncio
async def test_flat_files_are_ignored_once_the_marker_exists(repo, tmp_path):
    _flat(tmp_path, _entry("old-a", A, "2026-09-01T00:00:00"))
    (tmp_path / LAYOUT_MARKER).write_text("1", encoding="utf-8")

    assert (await repo.list(A, limit=50, offset=0))[1] == 0


@pytest.mark.asyncio
async def test_erase_also_removes_the_owners_flat_files(repo, tmp_path):
    _flat(tmp_path, _entry("old-a", A, "2026-09-01T00:00:00"))
    _flat(tmp_path, _entry("old-b", B, "2026-09-02T00:00:00"))

    assert await repo.erase(A) == (1, 0)

    assert not (tmp_path / "old-a.json").exists()
    assert (tmp_path / "old-b.json").exists()


@pytest.mark.asyncio
async def test_erase_reports_a_flat_file_it_cannot_attribute(repo, tmp_path):
    (tmp_path / "torn.json").write_text("{not json", encoding="utf-8")

    assert await repo.erase(A) == (0, 1), "an unreadable flat file may be the caller's"
