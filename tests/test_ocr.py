"""Tests for OCR-enhanced file extraction."""

import io

# Create an authenticated client for tests
import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from reasoner.api import app
from reasoner.core.settings import settings
from reasoner.infrastructure.auth import set_auth_adapter
from reasoner.infrastructure.auth.local_adapter import LocalAuthAdapter
from reasoner.infrastructure.uploader import SCANNED_PDF_OCR_UNAVAILABLE
from reasoner.uploader import (
    extract_text,
    save_uploaded_file,
    save_uploaded_files,
)

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-local-auth-adapter-only")
_adapter = LocalAuthAdapter()
# Force LocalAuthAdapter regardless of ambient SUPABASE_URL/ENVIRONMENT config —
# get_auth_adapter() otherwise picks SupabaseAuthAdapter outside ENVIRONMENT=testing.
set_auth_adapter(_adapter)
_test_token = _adapter.create_token("11111111-1111-1111-1111-111111111111", "test@example.com")
client = TestClient(app, headers={"Authorization": f"Bearer {_test_token}"})


@pytest.fixture(autouse=True)
def _pin_auth_adapter():
    """Re-install this module's adapter before every test in it.

    set_auth_adapter() above runs once, at import. The adapter it sets is a
    process global, and other modules replace it from inside fixtures at test
    time (test_saas_quota_integration.py sets its own and then clears it), so on
    an xdist worker that ran those first, _test_token below was validated
    against the wrong adapter and every request here came back 401. Pinning it
    per test makes this module independent of whatever ran before it.
    """
    set_auth_adapter(_adapter)
    yield


def _build_minimal_pdf(text: str) -> bytes:
    """Build a tiny single-page PDF with real, extractable text using only
    pypdf (no reportlab / external renderer — pypdf's writer can assemble a
    valid content stream against a standard 14 font that needs no embedding).
    """
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)

    font_dict = DictionaryObject()
    font_dict.update({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    font_ref = writer._add_object(font_dict)

    fonts = DictionaryObject()
    fonts[NameObject("/F1")] = font_ref
    resources = DictionaryObject()
    resources[NameObject("/Font")] = fonts
    page[NameObject("/Resources")] = resources

    content = DecodedStreamObject()
    content.set_data(f"BT /F1 18 Tf 20 100 Td ({text}) Tj ET".encode("latin-1"))
    page[NameObject("/Contents")] = writer._add_object(content)

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


class TestRealPdfTextExtraction:
    """Regression test: pypdf (not PyMuPDF/fitz) drives PDF text extraction
    through the real production path (extract_text -> _extract_pdf ->
    pypdf.PdfReader), using a PDF built with pypdf itself rather than a
    fixture file or a mocked reader."""

    @pytest.mark.asyncio
    async def test_extract_text_reads_real_pdf_via_pypdf(self):
        # >= 50 extracted chars so extract_text() returns the text-layer
        # result directly instead of falling through to the (now-degraded)
        # scanned-PDF OCR path.
        pdf_text = "Hello pypdf, this is a real generated PDF with enough extractable text."
        pdf_bytes = _build_minimal_pdf(pdf_text)
        result = await extract_text(pdf_bytes, "generated.pdf")
        assert pdf_text in result

    @pytest.mark.asyncio
    async def test_extract_pdf_directly_via_pypdf(self):
        """_extract_pdf() itself (the pypdf.PdfReader call site) round-trips
        real PDF bytes regardless of the >= 50 char OCR-fallback threshold."""
        from reasoner.infrastructure.uploader import _extract_pdf
        pdf_bytes = _build_minimal_pdf("Short text")
        result = _extract_pdf(pdf_bytes)
        assert "Short text" in result


class TestShortPdfKeepsPypdfText:
    """A short text-layer PDF (< 50 chars) or force_ocr must not have its
    pypdf text discarded in favour of the 'OCR unavailable' notice."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("force_ocr", [False, True])
    async def test_short_real_pdf_returns_pypdf_text(self, force_ocr):
        pdf_bytes = _build_minimal_pdf("Short text")  # ~10 chars, below threshold
        result = await extract_text(pdf_bytes, "short.pdf", force_ocr=force_ocr)
        assert "Short text" in result
        assert result != SCANNED_PDF_OCR_UNAVAILABLE

    @pytest.mark.asyncio
    @pytest.mark.parametrize("force_ocr", [False, True])
    async def test_pdf_without_text_returns_unavailable_notice(self, force_ocr):
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        buf = io.BytesIO()
        writer.write(buf)
        result = await extract_text(buf.getvalue(), "blank.pdf", force_ocr=force_ocr)
        assert result == SCANNED_PDF_OCR_UNAVAILABLE

    @pytest.mark.asyncio
    @pytest.mark.parametrize("force_ocr", [False, True])
    async def test_corrupt_pdf_keeps_real_error(self, force_ocr):
        result = await extract_text(b"not a pdf at all", "bad.pdf", force_ocr=force_ocr)
        assert result.startswith("[PDF extraction failed:")
        assert result != SCANNED_PDF_OCR_UNAVAILABLE


class TestExtractTextOCR:
    """Unit tests for OCR dispatch in extract_text()."""

    @pytest.mark.asyncio
    async def test_txt_ignores_force_ocr(self):
        """Text files should never use OCR regardless of force_ocr."""
        content = b"Hello world"
        result = await extract_text(content, "test.txt", force_ocr=True)
        assert result == "Hello world"

    @pytest.mark.asyncio
    async def test_image_uses_describe_by_default(self):
        """Images without force_ocr should use describe_image."""
        with patch("reasoner.infrastructure.uploader._extract_image", new_callable=AsyncMock) as mock_describe:
            mock_describe.return_value = "A photo of a cat"
            result = await extract_text(b"fake-img", "test.png")
            mock_describe.assert_awaited_once_with(b"fake-img", "test.png")
            assert result == "A photo of a cat"

    @pytest.mark.asyncio
    async def test_image_uses_ocr_when_forced(self):
        """Images with force_ocr=True should use ocr_image."""
        with patch("reasoner.infrastructure.uploader._ocr_image", new_callable=AsyncMock) as mock_ocr:
            mock_ocr.return_value = "Hello from image"
            result = await extract_text(b"fake-img", "test.png", force_ocr=True)
            mock_ocr.assert_awaited_once_with(b"fake-img", "test.png")
            assert result == "Hello from image"

    @pytest.mark.asyncio
    async def test_pdf_uses_ocr_when_forced(self):
        """PDFs with force_ocr=True should always route to OCR."""
        with patch("reasoner.infrastructure.uploader._extract_pdf") as mock_pdf, \
             patch("reasoner.infrastructure.uploader._ocr_scanned_pdf", new_callable=AsyncMock) as mock_ocr:
            mock_pdf.return_value = "Plenty of text here that would normally skip OCR"
            mock_ocr.return_value = "OCR text"
            result = await extract_text(b"fake-pdf", "test.pdf", force_ocr=True)
            mock_ocr.assert_awaited_once_with(b"fake-pdf")
            assert result == "OCR text"

    @pytest.mark.asyncio
    async def test_pdf_skips_ocr_when_text_is_long(self):
        """PDFs with extracted text >= 50 chars should skip OCR."""
        long_text = "x" * 50
        with patch("reasoner.infrastructure.uploader._extract_pdf") as mock_pdf, \
             patch("reasoner.infrastructure.uploader._ocr_scanned_pdf", new_callable=AsyncMock) as mock_ocr:
            mock_pdf.return_value = long_text
            result = await extract_text(b"fake-pdf", "test.pdf")
            assert result == long_text
            mock_ocr.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_pdf_fallback_to_ocr_when_text_is_short(self):
        """PDFs with extracted text < 50 chars should trigger OCR fallback."""
        with patch("reasoner.infrastructure.uploader._extract_pdf") as mock_pdf, \
             patch("reasoner.infrastructure.uploader._ocr_scanned_pdf", new_callable=AsyncMock) as mock_ocr:
            mock_pdf.return_value = "short"
            mock_ocr.return_value = "Scanned page text"
            result = await extract_text(b"fake-pdf", "test.pdf")
            mock_ocr.assert_awaited_once_with(b"fake-pdf")
            assert result == "Scanned page text"

    @pytest.mark.asyncio
    async def test_pdf_fallback_whitespace_only_counts_as_short(self):
        """PDFs returning only whitespace should trigger OCR fallback."""
        with patch("reasoner.infrastructure.uploader._extract_pdf") as mock_pdf, \
             patch("reasoner.infrastructure.uploader._ocr_scanned_pdf", new_callable=AsyncMock) as mock_ocr:
            mock_pdf.return_value = "   \n\n   "
            mock_ocr.return_value = "Scanned page text"
            result = await extract_text(b"fake-pdf", "test.pdf")
            mock_ocr.assert_awaited_once_with(b"fake-pdf")
            assert result == "Scanned page text"


class TestOCRScannedPDF:
    """Unit tests for _ocr_scanned_pdf().

    PyMuPDF (fitz) was removed in favor of pypdf (BSD-3-Clause) to drop an
    AGPL dependency from the shipped image. pypdf has no PDF-page-
    rasterization API, so page-image OCR for scanned PDFs has no equivalent
    and is now an explicit, always-on degradation rather than an
    ImportError-triggered one. These tests cover that degraded contract.
    """

    @pytest.mark.asyncio
    async def test_ocr_scanned_pdf_returns_explicit_degradation_message(self):
        """Scanned-PDF OCR always returns a clear, user-visible unavailable message."""
        from reasoner.uploader import _ocr_scanned_pdf
        result = await _ocr_scanned_pdf(b"fake-pdf")
        assert result == SCANNED_PDF_OCR_UNAVAILABLE
        assert "unavailable" in result
        # Neutral: no build/licensing detail in user-visible, indexable content.
        assert "PyMuPDF" not in result
        assert "AGPL" not in result

    @pytest.mark.asyncio
    async def test_ocr_scanned_pdf_logs_warning(self):
        """The degradation is logged, not silent."""
        from reasoner.uploader import _ocr_scanned_pdf
        with patch("reasoner.infrastructure.uploader.logger") as mock_logger:
            await _ocr_scanned_pdf(b"fake-pdf")
            mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_ocr_scanned_pdf_does_not_call_ocr_image(self):
        """No page images exist to OCR, so _ocr_image must never be invoked."""
        from reasoner.uploader import _ocr_scanned_pdf
        with patch("reasoner.infrastructure.uploader._ocr_image", new_callable=AsyncMock) as mock_ocr:
            await _ocr_scanned_pdf(b"fake-pdf")
            mock_ocr.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ocr_scanned_pdf_accepts_max_pages_kwarg(self):
        """max_pages is still accepted for call-site compatibility, though unused."""
        from reasoner.uploader import _ocr_scanned_pdf
        result = await _ocr_scanned_pdf(b"fake-pdf", max_pages=5)
        assert result == SCANNED_PDF_OCR_UNAVAILABLE


class TestSaveUploadedFileOCR:
    """Integration tests for force_ocr parameter plumbing."""

    @pytest.mark.asyncio
    async def test_save_uploaded_file_passes_force_ocr(self, tmp_path):
        """force_ocr should be forwarded to extract_text."""
        with patch("reasoner.infrastructure.uploader.UPLOAD_DIR", tmp_path), \
             patch("reasoner.infrastructure.uploader._MAGIC_AVAILABLE", False), \
             patch.object(settings, "UPLOAD_REQUIRE_MIME_VALIDATION", False), \
             patch("reasoner.infrastructure.uploader.extract_text", new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = "OCR result"
            result = await save_uploaded_file(b"fake", "img.png", force_ocr=True)
            assert result["text"] == "OCR result"
            mock_extract.assert_awaited_once()
            # Check force_ocr was passed
            assert mock_extract.call_args.kwargs.get("force_ocr") is True

    @pytest.mark.asyncio
    async def test_save_uploaded_files_passes_force_ocr(self, tmp_path):
        """force_ocr should be forwarded for batched uploads."""
        with patch("reasoner.infrastructure.uploader.UPLOAD_DIR", tmp_path), \
             patch("reasoner.infrastructure.uploader._MAGIC_AVAILABLE", False), \
             patch.object(settings, "UPLOAD_REQUIRE_MIME_VALIDATION", False), \
             patch("reasoner.infrastructure.uploader.extract_text", new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = "OCR result"
            results = await save_uploaded_files(
                [(b"fake1", "a.png"), (b"fake2", "b.png")],
                force_ocr=True,
            )
            assert len(results) == 2
            assert all(r["text"] == "OCR result" for r in results)
            assert mock_extract.await_count == 2


class TestUnavailableNoticeNotIndexed:
    @pytest.mark.asyncio
    async def test_bare_unavailable_notice_is_not_indexed(self, tmp_path):
        with patch("reasoner.infrastructure.uploader.UPLOAD_DIR", tmp_path),              patch("reasoner.infrastructure.uploader._MAGIC_AVAILABLE", False),              patch.object(settings, "UPLOAD_REQUIRE_MIME_VALIDATION", False),              patch.object(settings, "DOCUMENT_SEMANTIC_RETRIEVAL_ENABLED", True),              patch("reasoner.infrastructure.documents.index_queue.enqueue_index_job") as enqueue,              patch("reasoner.infrastructure.uploader.extract_text", new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = SCANNED_PDF_OCR_UNAVAILABLE
            result = await save_uploaded_file(b"%PDF-fake", "scan.pdf")
            assert result["success"] is True
            enqueue.assert_not_called()

    @pytest.mark.asyncio
    async def test_real_text_is_still_indexed(self, tmp_path):
        with patch("reasoner.infrastructure.uploader.UPLOAD_DIR", tmp_path),              patch("reasoner.infrastructure.uploader._MAGIC_AVAILABLE", False),              patch.object(settings, "UPLOAD_REQUIRE_MIME_VALIDATION", False),              patch.object(settings, "DOCUMENT_SEMANTIC_RETRIEVAL_ENABLED", True),              patch("reasoner.infrastructure.documents.index_queue.enqueue_index_job") as enqueue,              patch("reasoner.infrastructure.uploader.extract_text", new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = "real content"
            await save_uploaded_file(b"%PDF-fake", "doc.pdf")
            enqueue.assert_called_once()


class TestUploadEndpointOCR:
    """Tests for the upload API endpoint with force_ocr."""

    def test_upload_without_force_ocr(self):
        """Default upload should not pass force_ocr=True."""
        with patch("reasoner.api.routes.uploads.save_uploaded_file", new_callable=AsyncMock) as mock_save:
            mock_save.return_value = {
                "success": True,
                "file_id": "abc123",
                "filename": "test.png",
                "size": 4,
                "mime_type": "image/png",
                "text": "desc",
                "path": "/tmp/test.png",
            }
            response = client.post(
                "/api/upload",
                files={"file": ("test.png", io.BytesIO(b"fake"), "image/png")},
            )
            assert response.status_code == 200
            mock_save.assert_awaited_once_with(b"fake", "test.png", user_id="11111111-1111-1111-1111-111111111111", force_ocr=False)

    def test_upload_with_force_ocr(self):
        """Upload with ?force_ocr=true should pass force_ocr=True."""
        with patch("reasoner.api.routes.uploads.save_uploaded_file", new_callable=AsyncMock) as mock_save:
            mock_save.return_value = {
                "success": True,
                "file_id": "abc123",
                "filename": "test.png",
                "size": 4,
                "mime_type": "image/png",
                "text": "OCR text",
                "path": "/tmp/test.png",
            }
            response = client.post(
                "/api/upload?force_ocr=true",
                files={"file": ("test.png", io.BytesIO(b"fake"), "image/png")},
            )
            assert response.status_code == 200
            mock_save.assert_awaited_once_with(b"fake", "test.png", user_id="11111111-1111-1111-1111-111111111111", force_ocr=True)

    def test_upload_batch_with_force_ocr(self):
        """Batch upload with ?force_ocr=true should pass force_ocr=True."""
        with patch("reasoner.api.routes.uploads.save_uploaded_files", new_callable=AsyncMock) as mock_save:
            mock_save.return_value = [
                {
                    "success": True,
                    "file_id": "abc123",
                    "filename": "a.png",
                    "size": 4,
                    "mime_type": "image/png",
                    "text": "OCR text",
                    "path": "/tmp/a.png",
                },
                {
                    "success": True,
                    "file_id": "def456",
                    "filename": "b.png",
                    "size": 4,
                    "mime_type": "image/png",
                    "text": "OCR text 2",
                    "path": "/tmp/b.png",
                },
            ]
            response = client.post(
                "/api/upload?force_ocr=true",
                files=[
                    ("file", ("a.png", io.BytesIO(b"fake1"), "image/png")),
                    ("file", ("b.png", io.BytesIO(b"fake2"), "image/png")),
                ],
            )
            assert response.status_code == 200
            mock_save.assert_awaited_once()
            assert mock_save.call_args.kwargs.get("force_ocr") is True
