"""Audit 8 data / filesystem / GDPR findings: one test (or few) per fix."""

from __future__ import annotations

import gzip
import inspect
import json
import struct
import subprocess
import sys
import threading
import zlib
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

UID = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"


# ── 1. image walks: capped, aggregated, off the event loop ───────────────


def _chunk(ctype: bytes, payload: bytes = b"") -> bytes:
    crc = struct.pack(">I", zlib.crc32(ctype + payload))
    return struct.pack(">I", len(payload)) + ctype + payload + crc


_PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _png(n_text: int) -> bytes:
    return _PNG_SIG + _chunk(b"IHDR", b"\x00" * 13) + _chunk(b"tEXt") * n_text + _chunk(b"IEND")


def test_png_with_millions_of_chunks_is_refused_not_walked():
    from reasoner.infrastructure.watermark.image import png
    from reasoner.infrastructure.watermark.image.markers import (
        MAX_STRUCTURES,
        ImageStructureLimitError,
    )

    data = _png(MAX_STRUCTURES + 1)
    with pytest.raises(ImageStructureLimitError):
        png.inspect(data)
    with pytest.raises(ImageStructureLimitError):
        png.strip(data)


def test_scrubber_degrades_instead_of_walking_an_oversized_png():
    from reasoner.infrastructure.watermark.image.markers import MAX_STRUCTURES
    from reasoner.infrastructure.watermark.scrubber import ImageMarkScrubber

    outcome = ImageMarkScrubber().scrub(_png(MAX_STRUCTURES + 1))

    assert outcome.degraded and "too many PNG chunks" in outcome.degraded_reason


def test_png_strip_reports_counts_not_one_line_per_chunk():
    from reasoner.infrastructure.watermark.image import png

    _, actions = png.strip(_png(500))

    assert actions == ("drop PNG chunk tEXt (x500)",)


def test_isobmff_box_flood_is_refused():
    from reasoner.infrastructure.watermark.image import isobmff
    from reasoner.infrastructure.watermark.image.markers import (
        MAX_STRUCTURES,
        ImageStructureLimitError,
    )

    data = struct.pack(">I", 8) + b"free"
    with pytest.raises(ImageStructureLimitError):
        isobmff._parse_boxes(data * (MAX_STRUCTURES + 1))


def test_jpeg_segment_flood_is_refused():
    from reasoner.infrastructure.watermark.image import jpeg
    from reasoner.infrastructure.watermark.image.markers import (
        MAX_STRUCTURES,
        ImageStructureLimitError,
    )

    data = b"\xff\xd8" + b"\xff\xfe\x00\x02" * (MAX_STRUCTURES + 1) + b"\xff\xd9"
    with pytest.raises(ImageStructureLimitError):
        jpeg.strip(data)


async def test_provenance_routes_walk_the_image_off_the_event_loop(monkeypatch):
    from reasoner.api.routes import provenance

    main = threading.get_ident()
    seen: list[int] = []

    class _Svc:
        def inspect_image(self, data):
            seen.append(threading.get_ident())
            return SimpleNamespace(to_dict=lambda: {"ok": True})

        def scrub_image(self, data, policy):
            seen.append(threading.get_ident())
            return SimpleNamespace(to_dict=lambda: {}, data=data)

    monkeypatch.setattr(provenance, "_decode_image", lambda image: ("image/png", b"x"))
    body = provenance.ProvenanceScrubRequest(image="data:image/png;base64,AA==")

    await provenance.inspect(body, service=_Svc())
    await provenance.scrub(body, service=_Svc())

    assert len(seen) == 2 and main not in seen


async def test_inspect_answers_422_for_a_structure_flood(monkeypatch):
    from fastapi import HTTPException

    from reasoner.api.routes import provenance
    from reasoner.infrastructure.watermark.image.markers import ImageStructureLimitError

    class _Svc:
        def inspect_image(self, data):
            raise ImageStructureLimitError("PNG chunks")

    monkeypatch.setattr(provenance, "_decode_image", lambda image: ("image/png", b"x"))
    with pytest.raises(HTTPException) as exc:
        await provenance.inspect(
            provenance.ProvenanceContentRequest(image="data:image/png;base64,AA=="), service=_Svc()
        )
    assert exc.value.status_code == 422


# ── 2. persistent directories come from settings ─────────────────────────


def _env_probe(code: str, **env: str) -> str:
    import os

    run = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=120,
        env={**os.environ, **env, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )
    assert run.returncode == 0, run.stderr
    return run.stdout.strip().splitlines()[-1]


def test_history_and_run_cache_dirs_follow_their_settings(tmp_path):
    out = _env_probe(
        "from reasoner.api.history import HISTORY_DIR; from reasoner.api.cache import CACHE_DIR;"
        "print(HISTORY_DIR, CACHE_DIR)",
        HISTORY_STORAGE_DIR=str(tmp_path / "h" / "runs"), RUN_CACHE_DIR=str(tmp_path / "c"),
    )
    assert out == f"{tmp_path / 'h' / 'runs'} {tmp_path / 'c'}"


def test_neuro_data_dir_follows_its_setting(monkeypatch, tmp_path):
    from reasoner.core.settings import settings
    from reasoner.neuro.config import NeuroConfig, _apply_defaults

    monkeypatch.setattr(settings, "NEURO_DATA_DIR", str(tmp_path / "neuro"))

    assert _apply_defaults(NeuroConfig()).data_dir == str(tmp_path / "neuro")


# ── 3. run-replay cache is per owner and erasable ────────────────────────


@pytest.fixture
def run_cache(monkeypatch, tmp_path):
    from reasoner.api import cache

    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path / "cache")
    (tmp_path / "cache").mkdir()
    cache._MEMORY_CACHE.clear()
    yield cache
    cache._MEMORY_CACHE.clear()


async def test_run_cache_is_stored_per_owner_and_erased_with_the_owner(run_cache):
    events = [{"type": "done", "solution": "secret synthesis"}]
    await run_cache._save_cache("k1", events, user_id=UID)
    await run_cache._save_cache("k2", events, user_id=OTHER)

    assert await run_cache._load_cache("k1", user_id=UID) == events
    assert [r["key"] for r in run_cache.export_owner_cache(UID)] == ["k1"]
    assert not list(run_cache.CACHE_DIR.glob("*.json"))  # nothing owned sits at the root

    assert run_cache.erase_owner_cache(UID) == 0

    assert run_cache.export_owner_cache(UID) == []
    assert await run_cache._load_cache("k1", user_id=UID) is None  # memory copy gone too
    assert await run_cache._load_cache("k2", user_id=OTHER) == events


async def test_admin_clear_reaches_owned_entries(run_cache):
    await run_cache._save_cache("k1", [{"type": "done"}], user_id=UID)
    await run_cache._save_cache("anon", [{"type": "done"}])

    assert run_cache.clear_disk_cache() == 2


def test_registry_holds_both_cache_stores():
    from reasoner.api.user_data import user_data_stores

    names = [s.name for s in user_data_stores()]
    assert {"run_cache", "token_cache"} <= set(names)


# ── 3/4. token cache: per owner, tenant survives a reload ────────────────


async def test_token_cache_persists_agent_id_so_a_reload_keeps_the_tenant_guard(tmp_path):
    from reasoner.infrastructure.token_cache import TokenAwareCache

    prompt = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
    first = TokenAwareCache(cache_dir=tmp_path)
    await first.set("p", "ph", "m", prompt, "owner secret", 10, agent_id=UID)

    reloaded = TokenAwareCache(cache_dir=tmp_path)
    near_miss = prompt + " lambda"  # not an exact hit: exercises the semantic scan

    assert await reloaded.get("p", "ph", "m", near_miss, agent_id="") is None
    assert await reloaded.get("p", "ph", "m", near_miss, agent_id=UID) == "owner secret"


async def test_token_cache_erase_and_export_cover_one_owner(tmp_path):
    from reasoner.infrastructure.token_cache import TokenAwareCache

    cache = TokenAwareCache(cache_dir=tmp_path)
    await cache.set("p", "ph", "m", "prompt one", "resp one", 5, agent_id=UID)
    await cache.set("p", "ph", "m", "prompt two", "resp two", 5, agent_id=OTHER)

    exported = await cache.export_owner(UID)
    assert [e["response"] for e in exported] == ["resp one"]

    assert await cache.erase_owner(UID) == 0

    assert await cache.export_owner(UID) == []
    assert await cache.get("p", "ph", "m", "prompt one", agent_id=UID) is None
    assert await cache.get("p", "ph", "m", "prompt two", agent_id=OTHER) == "resp two"
    fresh = TokenAwareCache(cache_dir=tmp_path)
    assert await fresh.export_owner(UID) == []
    assert [e["response"] for e in await fresh.export_owner(OTHER)] == ["resp two"]


# ── 5. exports are not truncated ─────────────────────────────────────────


async def test_pg_export_pages_through_every_row():
    import re

    from reasoner.infrastructure.persistence.user_data_pg import EXPORT_PAGE_SIZE, PgUserDataStore

    total = EXPORT_PAGE_SIZE * 2 + 37
    rows = [{"preset": "p", "method": "m", "tokens_in": i, "tokens_out": 0,
             "cost_usd": 0, "created_at": i} for i in range(total)]

    class _Pool:
        async def fetch(self, sql, *args):
            offset = int(re.search(r"OFFSET (\d+)", sql).group(1))
            limit = int(re.search(r"LIMIT (\d+)", sql).group(1))
            return rows[offset:offset + limit]

    async def pool():
        return _Pool()

    store = PgUserDataStore("query_log", "query_log", "user_id", pool, order_by="created_at")
    out = await store.export(UID)

    assert len(out) == total


async def test_history_export_pages_through_every_entry():
    from reasoner.infrastructure.persistence.user_data_local import HistoryStore

    entries = [{"id": str(i)} for i in range(1234)]

    class _Repo:
        async def list(self, owner, limit, offset):
            return entries[offset:offset + limit], len(entries)

    out = await HistoryStore(lambda: _Repo()).export(UID)

    assert len(out) == 1234


async def test_neuro_export_includes_session_logs(tmp_path):
    from reasoner.neuro.server import NeuroService

    tenant = tmp_path / "agents" / f"u-{UID}-conv"
    (tenant / "sessions" / "hot").mkdir(parents=True)
    (tenant / "sessions" / "warm").mkdir()
    (tenant / "sessions" / "cold").mkdir()
    (tenant / "sessions" / "hot" / "s1.jsonl").write_text(
        json.dumps({"prompt": "hot question"}) + "\n", encoding="utf-8")
    (tenant / "sessions" / "warm" / "s2.json").write_text(
        json.dumps({"summary": "warm summary"}), encoding="utf-8")
    (tenant / "sessions" / "cold" / "s3.jsonl.gz").write_bytes(
        gzip.compress((json.dumps({"prompt": "cold question"}) + "\n").encode()))
    (tenant / "l2").mkdir()
    (tenant / "l2" / "index.json").write_text(
        json.dumps([{"id": "a", "content": "memory"}]), encoding="utf-8")

    service = NeuroService.__new__(NeuroService)
    service.config = SimpleNamespace(data_dir=str(tmp_path))

    out = (await service.export_owner(UID))[f"u-{UID}-conv"]

    assert out["memory"][0]["content"] == "memory"
    assert out["sessions"]["hot"]["s1.jsonl"] == [{"prompt": "hot question"}]
    assert out["sessions"]["warm"]["s2.json"] == {"summary": "warm summary"}
    assert out["sessions"]["cold"]["s3.jsonl.gz"] == [{"prompt": "cold question"}]


# ── 6. blocking upload-index work stays off the loop ─────────────────────


async def test_delete_route_runs_the_blocking_delete_in_a_thread(monkeypatch):
    from reasoner.api.routes import uploads

    main = threading.get_ident()
    seen: list[int] = []

    def _delete(file_id, user_id=None):
        seen.append(threading.get_ident())
        return True

    class _Usage:
        async def adjust(self, *_):
            return None

    monkeypatch.setattr(uploads, "delete_file", _delete)
    monkeypatch.setattr(uploads, "file_stored_bytes", lambda fid: 0)
    monkeypatch.setattr(uploads, "get_upload_usage_repo", lambda: _Usage())

    out = await uploads.delete_uploaded_file(
        "abc-123", user=SimpleNamespace(id=UID), rate_limit_checked=None
    )

    assert out == {"status": "deleted"} and seen and main not in seen


# ── 7. shared files are written atomically ───────────────────────────────


async def test_neuro_l1_bundle_is_written_atomically(monkeypatch, tmp_path):
    from reasoner.neuro import cache as neuro_cache

    written: list[Path] = []
    real = neuro_cache.atomic_write_text
    monkeypatch.setattr(
        neuro_cache, "atomic_write_text", lambda p, t: (written.append(p), real(p, t))
    )

    await neuro_cache.L1Cache(tmp_path, neuro_cache.CacheConfig()).add("c", "s", [0.1])

    assert len(written) == 1 and written[0].parent == tmp_path


def test_vector_sidecar_is_written_atomically():
    from reasoner.documents import vector_store

    src = inspect.getsource(vector_store)
    assert "atomic_write_text(path" in src and "path.write_text(" not in src


# ── 8. a file trimmed mid-listing does not blank the history ─────────────


def test_history_listing_skips_an_entry_that_vanishes_mid_scan(monkeypatch, tmp_path):
    from reasoner.infrastructure.persistence import history_files

    class _Entry:
        def __init__(self, name, gone=False):
            self.name, self.path, self._gone = name, str(tmp_path / name), gone

        def stat(self):
            if self._gone:
                raise FileNotFoundError(self.path)
            return SimpleNamespace(st_mtime=1.0)

    class _Scan:
        def __enter__(self):
            return iter([_Entry("a.json"), _Entry("trimmed.json", gone=True), _Entry("b.json")])

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(history_files.os, "scandir", lambda path: _Scan())

    files = history_files.FileHistoryRepository(tmp_path)._files("owner")

    assert sorted(p.name for p in files) == ["a.json", "b.json"]
