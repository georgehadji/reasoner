"""Tests for OCR-enhanced file extraction."""

import io
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from reasoner.api import app
from reasoner.infrastructure.auth.local_adapter import LocalAuthAdapter
from reasoner.uploader import (
    extract_text,
    save_uploaded_file,
    save_uploaded_files,
    _extract_pdf,
)

# Create an authenticated client for tests
import os
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-local-auth-adapter-only")
_adapter = LocalAuthAdapter()
_test_token = _adapter.create_token("11111111-1111-1111-1111-111111111111", "test@example.com")
client = TestClient(app, headers={"Authorization": f"Bearer {_test_token}"})


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
        with patch("reasoner.uploader._extract_image", new_callable=AsyncMock) as mock_describe:
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
        with patch("reasoner.uploader._extract_pdf") as mock_pdf, \
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
        with patch("reasoner.uploader._extract_pdf") as mock_pdf, \
             patch("reasoner.infrastructure.uploader._ocr_scanned_pdf", new_callable=AsyncMock) as mock_ocr:
            mock_pdf.return_value = long_text
            result = await extract_text(b"fake-pdf", "test.pdf")
            assert result == long_text
            mock_ocr.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_pdf_fallback_to_ocr_when_text_is_short(self):
        """PDFs with extracted text < 50 chars should trigger OCR fallback."""
        with patch("reasoner.uploader._extract_pdf") as mock_pdf, \
             patch("reasoner.infrastructure.uploader._ocr_scanned_pdf", new_callable=AsyncMock) as mock_ocr:
            mock_pdf.return_value = "short"
            mock_ocr.return_value = "Scanned page text"
            result = await extract_text(b"fake-pdf", "test.pdf")
            mock_ocr.assert_awaited_once_with(b"fake-pdf")
            assert result == "Scanned page text"

    @pytest.mark.asyncio
    async def test_pdf_fallback_whitespace_only_counts_as_short(self):
        """PDFs returning only whitespace should trigger OCR fallback."""
        with patch("reasoner.uploader._extract_pdf") as mock_pdf, \
             patch("reasoner.infrastructure.uploader._ocr_scanned_pdf", new_callable=AsyncMock) as mock_ocr:
            mock_pdf.return_value = "   \n\n   "
            mock_ocr.return_value = "Scanned page text"
            result = await extract_text(b"fake-pdf", "test.pdf")
            mock_ocr.assert_awaited_once_with(b"fake-pdf")
            assert result == "Scanned page text"


class TestOCRScannedPDF:
    """Unit tests for _ocr_scanned_pdf()."""

    @pytest.mark.asyncio
    async def test_missing_pymupdf_returns_hint(self):
        """When fitz is unavailable, return install hint."""
        import builtins
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "fitz":
                raise ImportError("No module named fitz")
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", fake_import):
            from reasoner.uploader import _ocr_scanned_pdf
            result = await _ocr_scanned_pdf(b"fake")
            assert "install pymupdf" in result

    @pytest.mark.asyncio
    async def test_ocr_scanned_pdf_success(self):
        """Happy path: render pages and OCR them."""
        mock_page = MagicMock()
        mock_pix = MagicMock()
        mock_pix.tobytes.return_value = b"png-bytes"
        mock_page.get_pixmap.return_value = mock_pix
        mock_doc = MagicMock()
        mock_doc.__len__ = lambda self: 2
        mock_doc.load_page.return_value = mock_page

        with patch("reasoner.infrastructure.uploader._ocr_image", new_callable=AsyncMock) as mock_ocr:
            mock_ocr.return_value = "Page text"
            with patch("fitz.open", return_value=mock_doc):
                from reasoner.uploader import _ocr_scanned_pdf
                result = await _ocr_scanned_pdf(b"fake-pdf", max_pages=3)
                assert result == "Page text\n\nPage text"
                assert mock_ocr.await_count == 2

    @pytest.mark.asyncio
    async def test_ocr_scanned_pdf_respects_max_pages(self):
        """max_pages should limit the number of pages OCR'd."""
        mock_page = MagicMock()
        mock_pix = MagicMock()
        mock_pix.tobytes.return_value = b"png-bytes"
        mock_page.get_pixmap.return_value = mock_pix
        mock_doc = MagicMock()
        mock_doc.__len__ = lambda self: 5
        mock_doc.load_page.return_value = mock_page

        with patch("reasoner.infrastructure.uploader._ocr_image", new_callable=AsyncMock) as mock_ocr:
            mock_ocr.return_value = "Page text"
            with patch("fitz.open", return_value=mock_doc):
                from reasoner.uploader import _ocr_scanned_pdf
                result = await _ocr_scanned_pdf(b"fake-pdf", max_pages=2)
                assert mock_ocr.await_count == 2

    @pytest.mark.asyncio
    async def test_ocr_scanned_pdf_skips_failed_pages(self):
        """Pages returning bracket-wrapped errors should be skipped."""
        mock_page = MagicMock()
        mock_pix = MagicMock()
        mock_pix.tobytes.return_value = b"png-bytes"
        mock_page.get_pixmap.return_value = mock_pix
        mock_doc = MagicMock()
        mock_doc.__len__ = lambda self: 2
        mock_doc.load_page.return_value = mock_page

        with patch("reasoner.infrastructure.uploader._ocr_image", new_callable=AsyncMock) as mock_ocr:
            mock_ocr.side_effect = ["Good text", "[OCR failed]"]
            with patch("fitz.open", return_value=mock_doc):
                from reasoner.uploader import _ocr_scanned_pdf
                result = await _ocr_scanned_pdf(b"fake-pdf")
                assert result == "Good text"

    @pytest.mark.asyncio
    async def test_ocr_scanned_pdf_all_pages_fail(self):
        """When all pages fail, return a fallback message."""
        mock_page = MagicMock()
        mock_pix = MagicMock()
        mock_pix.tobytes.return_value = b"png-bytes"
        mock_page.get_pixmap.return_value = mock_pix
        mock_doc = MagicMock()
        mock_doc.__len__ = lambda self: 1
        mock_doc.load_page.return_value = mock_page

        with patch("reasoner.infrastructure.uploader._ocr_image", new_callable=AsyncMock) as mock_ocr:
            mock_ocr.return_value = "[OCR failed]"
            with patch("fitz.open", return_value=mock_doc):
                from reasoner.uploader import _ocr_scanned_pdf
                result = await _ocr_scanned_pdf(b"fake-pdf")
                assert "no text could be extracted" in result


class TestSaveUploadedFileOCR:
    """Integration tests for force_ocr parameter plumbing."""

    @pytest.mark.asyncio
    async def test_save_uploaded_file_passes_force_ocr(self, tmp_path):
        """force_ocr should be forwarded to extract_text."""
        with patch("reasoner.infrastructure.uploader._UPLOAD_DIR", tmp_path), \
             patch("reasoner.infrastructure.uploader._MAGIC_AVAILABLE", False), \
             patch("reasoner.uploader.extract_text", new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = "OCR result"
            result = await save_uploaded_file(b"fake", "img.png", force_ocr=True)
            assert result["text"] == "OCR result"
            mock_extract.assert_awaited_once()
            # Check force_ocr was passed
            assert mock_extract.call_args.kwargs.get("force_ocr") is True

    @pytest.mark.asyncio
    async def test_save_uploaded_files_passes_force_ocr(self, tmp_path):
        """force_ocr should be forwarded for batched uploads."""
        with patch("reasoner.infrastructure.uploader._UPLOAD_DIR", tmp_path), \
             patch("reasoner.infrastructure.uploader._MAGIC_AVAILABLE", False), \
             patch("reasoner.uploader.extract_text", new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = "OCR result"
            results = await save_uploaded_files(
                [(b"fake1", "a.png"), (b"fake2", "b.png")],
                force_ocr=True,
            )
            assert len(results) == 2
            assert all(r["text"] == "OCR result" for r in results)
            assert mock_extract.await_count == 2


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
