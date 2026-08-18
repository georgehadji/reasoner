"""Integration tests for /api/provenance/* -- auth/CSRF/rate-limit wiring,
capability accuracy, and end-to-end text/image scrub round-trips.

CSRF is disabled globally for the test suite (tests/conftest.py sets
CSRF_ENFORCE_BACKEND=false), matching every other route-level integration
test in this repo -- CSRF-specific behavior is covered once, centrally, not
per-route.
"""

from __future__ import annotations

import base64
import struct

from fastapi.testclient import TestClient

from reasoner.api import app

client = TestClient(app)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_DUMMY_CRC = b"\x00\x00\x00\x00"
_MINIMAL_IHDR_PAYLOAD = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)


def _chunk(ctype: bytes, payload: bytes = b"") -> bytes:
    return struct.pack(">I", len(payload)) + ctype + payload + _DUMMY_CRC


def _minimal_png(*extra_chunks: bytes) -> bytes:
    return (
        PNG_SIGNATURE
        + _chunk(b"IHDR", _MINIMAL_IHDR_PAYLOAD)
        + b"".join(extra_chunks)
        + _chunk(b"IDAT", b"\x00")
        + _chunk(b"IEND")
    )


def _png_data_url(*extra_chunks: bytes) -> str:
    raw = base64.b64encode(_minimal_png(*extra_chunks)).decode("ascii")
    return f"data:image/png;base64,{raw}"


_PNG_WITH_TEXT_CHUNK = _png_data_url(_chunk(b"tEXt", b"Software\x00c2pa-demo"))


class TestCapabilities:
    def test_reports_supported_image_formats(self):
        response = client.get("/api/provenance/capabilities")
        assert response.status_code == 200
        body = response.json()
        assert set(body["image_formats"]) == {"png", "jpeg", "webp", "avif", "heic"}

    def test_pixel_backend_not_bound_by_default(self):
        body = client.get("/api/provenance/capabilities").json()
        assert body["pixel_backend_bound"] is False

    def test_layer_b_not_enabled(self):
        """Reported False regardless of settings -- no rewriter is bound yet (Phase 6)."""
        body = client.get("/api/provenance/capabilities").json()
        assert body["layer_b_enabled"] is False


class TestInspect:
    def test_requires_content_or_image(self):
        response = client.post("/api/provenance/inspect", json={})
        assert response.status_code == 422

    def test_inspects_clean_text(self):
        response = client.post("/api/provenance/inspect", json={"content": "hello world"})
        assert response.status_code == 200
        body = response.json()
        assert body["text"]["suspicious_total"] == 0
        assert "image" not in body

    def test_inspects_text_with_zero_width_space(self):
        text = "hello" + chr(0x200B) + "world"
        response = client.post("/api/provenance/inspect", json={"content": text})
        assert response.status_code == 200
        assert response.json()["text"]["suspicious_total"] >= 1

    def test_inspects_image_metadata(self):
        response = client.post("/api/provenance/inspect", json={"image": _PNG_WITH_TEXT_CHUNK})
        assert response.status_code == 200
        body = response.json()["image"]
        assert body["format"] == "png"

    def test_rejects_invalid_data_url(self):
        response = client.post("/api/provenance/inspect", json={"image": "not-a-data-url"})
        assert response.status_code == 400

    def test_rejects_oversized_image(self, monkeypatch):
        import reasoner.api.routes.provenance as provenance_module

        monkeypatch.setattr(provenance_module, "MAX_FILE_SIZE", 10)
        response = client.post("/api/provenance/inspect", json={"image": _PNG_WITH_TEXT_CHUNK})
        assert response.status_code == 413


class TestScrub:
    def test_requires_content_or_image(self):
        response = client.post("/api/provenance/scrub", json={})
        assert response.status_code == 422

    def test_scrubs_zero_width_space_from_text(self):
        text = "hello" + chr(0x200B) + "world"
        response = client.post("/api/provenance/scrub", json={"content": text})
        assert response.status_code == 200
        body = response.json()["text"]
        assert body["text"] == "helloworld"
        assert body["stats"]["removed_count"] >= 1

    def test_layer_a_false_leaves_text_unchanged(self):
        text = "hello" + chr(0x200B) + "world"
        response = client.post(
            "/api/provenance/scrub", json={"content": text, "layer_a": False}
        )
        assert response.status_code == 200
        body = response.json()["text"]
        assert body["text"] == text
        assert body["stats"]["removed_count"] == 0

    def test_scrubs_image_metadata_by_default(self):
        response = client.post("/api/provenance/scrub", json={"image": _PNG_WITH_TEXT_CHUNK})
        assert response.status_code == 200
        body = response.json()["image"]
        assert body["degraded"] is False
        assert "image" in body  # cleaned data URL present

    def test_image_metadata_false_returns_degraded_passthrough(self):
        response = client.post(
            "/api/provenance/scrub",
            json={"image": _PNG_WITH_TEXT_CHUNK, "image_metadata": False},
        )
        assert response.status_code == 200
        body = response.json()["image"]
        assert body["degraded"] is True

    def test_scrub_round_trip_reinspects_clean(self):
        scrub_response = client.post(
            "/api/provenance/scrub", json={"image": _PNG_WITH_TEXT_CHUNK}
        )
        cleaned_data_url = scrub_response.json()["image"]["image"]
        inspect_response = client.post(
            "/api/provenance/inspect", json={"image": cleaned_data_url}
        )
        assert inspect_response.json()["image"]["has_ai_metadata"] is False


class TestRewrite:
    def test_not_yet_implemented(self):
        response = client.post("/api/provenance/rewrite", json={})
        assert response.status_code == 501


__all__ = []
