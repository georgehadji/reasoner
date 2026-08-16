"""
Reasoner - File Upload Module
Handles file uploads and text extraction from PDF, TXT, DOCX files.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any, Optional

# Content-hash deduplication index: {sha256: file_id}
_HASH_INDEX_PATH = Path(__file__).parent / ".upload_hash_index.json"

# Retained references to background indexing tasks to prevent premature GC.
_BACKGROUND_TASKS: set[asyncio.Task] = set()

def _load_hash_index() -> dict[str, str]:
    if _HASH_INDEX_PATH.exists():
        try:
            return json.loads(_HASH_INDEX_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}

def _save_hash_index(index: dict[str, str]) -> None:
    try:
        _HASH_INDEX_PATH.write_text(json.dumps(index), encoding="utf-8")
    except OSError:
        pass

logger = logging.getLogger(__name__)

# Try to import optional dependencies
try:
    from pypdf import PdfReader
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    logger.warning("pypdf not available - PDF extraction disabled")

try:
    import docx
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    logger.warning("python-docx not available - DOCX extraction disabled")

# Upload storage directory
UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Maximum file size (50MB)
MAX_FILE_SIZE = 50 * 1024 * 1024

# Supported file extensions
SUPPORTED_EXTENSIONS = {".txt", ".pdf", ".docx", ".md", ".png", ".jpg", ".jpeg", ".webp"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

# MIME-type to extension mapping for validation
MIME_TYPE_MAP: dict[str, set[str]] = {
    "text/plain": {".txt"},
    "text/markdown": {".md"},
    "application/pdf": {".pdf"},
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {".docx"},
    "image/png": {".png"},
    "image/jpeg": {".jpg", ".jpeg"},
    "image/webp": {".webp"},
}

# Optional MIME-type validation via libmagic
try:
    import magic
    _MAGIC_AVAILABLE = True
except ImportError:
    _MAGIC_AVAILABLE = False
    logger.warning("python-magic not available — upload MIME-type validation disabled")


def _get_file_extension(filename: str) -> str:
    """Get the file extension from filename."""
    return Path(filename).suffix.lower()


def _is_allowed_file(filename: str) -> bool:
    """Check if file type is allowed."""
    return _get_file_extension(filename) in SUPPORTED_EXTENSIONS


def _extract_txt(content: bytes) -> str:
    """Extract text from plain text file."""
    return content.decode("utf-8", errors="replace")


def _extract_pdf(content: bytes) -> str:
    """Extract text from PDF file."""
    if not PDF_AVAILABLE:
        return "[PDF extraction not available - install pypdf]"

    try:
        import io
        reader = PdfReader(io.BytesIO(content))
        text_parts = []
        for page in reader.pages:
            text_parts.append(page.extract_text())
        return "\n".join(text_parts)
    except Exception as e:
        logger.error(f"PDF extraction failed: {e}")
        return f"[PDF extraction failed: {e}]"


def _extract_docx(content: bytes) -> str:
    """Extract text from DOCX file."""
    if not DOCX_AVAILABLE:
        return "[DOCX extraction not available - install python-docx]"
    
    try:
        import io
        from docx import Document
        doc = Document(io.BytesIO(content))
        text_parts = []
        for para in doc.paragraphs:
            if para.text.strip():
                text_parts.append(para.text)
        return "\n".join(text_parts)
    except Exception as e:
        logger.error(f"DOCX extraction failed: {e}")
        return f"[DOCX extraction failed: {e}]"


def _extract_md(content: bytes) -> str:
    """Extract text from markdown file."""
    return content.decode("utf-8", errors="replace")


async def _extract_image(content: bytes, filename: str) -> str:
    """Extract description from image via vision model captioning."""
    # Defer import to avoid circular dependencies at module load time
    try:
        from reasoner.infrastructure.llm.extraction import describe_image
        return await describe_image(content, filename)
    except Exception as e:
        logger.error(f"Image description failed: {e}")
        return f"[Image description failed: {e}]"


async def _ocr_image(content: bytes, filename: str) -> str:
    """Extract verbatim text from image via OCR-optimized model."""
    try:
        from reasoner.infrastructure.llm.extraction import ocr_image
        return await ocr_image(content, filename)
    except Exception as e:
        logger.error(f"Image OCR failed: {e}")
        return f"[Image OCR failed: {e}]"


def _render_pdf_pages_sync(content: bytes, max_pages: int) -> list[bytes]:
    """Render PDF pages to PNG bytes. Runs in a thread pool — all fitz I/O is sync."""
    import fitz
    doc = fitz.open(stream=content, filetype="pdf")
    try:
        images = []
        for page_num in range(min(max_pages, len(doc))):
            pix = doc.load_page(page_num).get_pixmap(dpi=200)
            images.append(pix.tobytes("png"))
        return images
    finally:
        doc.close()


async def _ocr_scanned_pdf(content: bytes, max_pages: int = 3) -> str:
    """Render PDF pages to images and OCR them."""
    try:
        import fitz  # noqa: F401 — availability check only
    except ImportError:
        return "[Scanned PDF detected — install pymupdf for OCR: pip install pymupdf]"

    try:
        page_images = await asyncio.to_thread(_render_pdf_pages_sync, content, max_pages)
        parts: list[str] = []
        for i, img_bytes in enumerate(page_images):
            page_text = await _ocr_image(img_bytes, f"page_{i}.png")
            if page_text and not page_text.startswith("["):
                parts.append(page_text)
        if not parts:
            return "[Scanned PDF — no text could be extracted]"
        return "\n\n".join(parts)
    except Exception as e:
        logger.error(f"Scanned PDF OCR failed: {e}")
        return f"[Scanned PDF OCR failed: {e}]"


async def _extract_text_unbounded(content: bytes, filename: str, *, force_ocr: bool = False) -> str:
    """
    Extract text content from a file based on its extension.

    Args:
        content: Raw file content bytes
        filename: Original filename to determine file type
        force_ocr: If True, use OCR instead of standard extraction for images and PDFs

    Returns:
        Extracted text content
    """
    ext = _get_file_extension(filename)

    match ext:
        case ".txt":
            return _extract_txt(content)
        case ".md":
            return _extract_md(content)
        case ".pdf":
            text = _extract_pdf(content)
            if not force_ocr and len(text.strip()) >= 50:
                return text
            return await _ocr_scanned_pdf(content)
        case ".docx":
            return _extract_docx(content)
        case ".png" | ".jpg" | ".jpeg" | ".webp":
            if force_ocr:
                return await _ocr_image(content, filename)
            return await _extract_image(content, filename)
        case _:
            return f"[Unsupported file type: {ext}]"


async def extract_text(content: bytes, filename: str, *, force_ocr: bool = False) -> str:
    """Extract content with a hard per-file parser/OCR timeout."""
    timeout = max(1, settings.DOCUMENT_EXTRACTION_TIMEOUT_SECONDS)
    try:
        return await asyncio.wait_for(
            _extract_text_unbounded(content, filename, force_ocr=force_ocr),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.warning("Document extraction timed out for %s after %ss", filename, timeout)
        return "[Document extraction timed out]"


async def save_uploaded_files(
    files: list[tuple[bytes, str]], user_id: str | None = None, *, force_ocr: bool = False
) -> list[dict[str, Any]]:
    """
    Save multiple uploaded files and extract their text content.

    Args:
        files: List of (content, filename) tuples
        user_id: Owner user ID
        force_ocr: If True, use OCR for images and scanned PDFs

    Returns:
        List of dictionaries with file info and extracted text
    """
    results = []
    for content, filename in files:
        result = await save_uploaded_file(content, filename, user_id=user_id, force_ocr=force_ocr)
        results.append(result)
    return results


async def save_uploaded_file(
    content: bytes, filename: str, user_id: str | None = None, *, force_ocr: bool = False
) -> dict[str, Any]:
    """
    Save an uploaded file and extract its text content.

    Args:
        content: Raw file content bytes
        filename: Original filename
        force_ocr: If True, use OCR for images and scanned PDFs

    Returns:
        Dictionary with file info and extracted text
    """
    # Validate file type
    if not _is_allowed_file(filename):
        return {
            "success": False,
            "error": f"File type not allowed. Supported: {', '.join(SUPPORTED_EXTENSIONS)}",
        }

    # Validate file size
    if len(content) > MAX_FILE_SIZE:
        return {
            "success": False,
            "error": f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB",
        }

    # Content-hash deduplication
    content_hash = hashlib.sha256(content).hexdigest()
    hash_index = _load_hash_index()
    existing_id = hash_index.get(content_hash)
    if existing_id:
        existing_path = UPLOAD_DIR / f"{existing_id}.meta.json"
        if existing_path.exists():
            logger.info("Deduplicating upload: hash %s matches existing file %s", content_hash[:16], existing_id)
            try:
                meta = json.loads(existing_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                meta = {}
            # Re-extract text for the new upload context (OCR settings may differ)
            text_content = await extract_text(content, filename, force_ocr=force_ocr)
            return {
                "success": True,
                "file_id": existing_id,
                "filename": filename,
                "size": len(content),
                "mime_type": meta.get("mime_type", "application/octet-stream"),
                "text": text_content,
                "path": str(UPLOAD_DIR / f"{existing_id}{_get_file_extension(filename)}"),
                "user_id": user_id,
                "deduplicated": True,
            }

    # Extract extension here so it's available for MIME validation below
    ext = _get_file_extension(filename)

    # Validate MIME type (defense against extension spoofing)
    if _MAGIC_AVAILABLE:
        detected_mime = magic.from_buffer(content, mime=True)
        allowed_exts = MIME_TYPE_MAP.get(detected_mime, set())
        if ext not in allowed_exts:
            logger.warning(
                "MIME-type mismatch: detected %s for declared extension %s",
                detected_mime,
                ext,
            )
            return {
                "success": False,
                "error": (
                    f"File content does not match extension. "
                    f"Detected: {detected_mime}, expected: {ext}"
                ),
            }
    else:
        logger.debug("Skipping MIME-type validation (python-magic not installed)")

    # Generate unique ID and create safe filename
    # FIX BUG-008: Prevent path traversal by using only the extension, not the full filename
    file_id = str(uuid.uuid4())[:12]
    ext = _get_file_extension(filename)
    
    # CRITICAL: Sanitize extension to prevent path traversal attacks
    # Only allow the last path component and validate it's a simple extension
    if not ext or not re.match(r'^\.[a-zA-Z0-9]+$', ext):
        return {
            "success": False,
            "error": "Invalid file extension",
        }
    
    # Safe filename: only UUID + validated extension
    safe_filename = f"{file_id}{ext}"
    file_path = UPLOAD_DIR / safe_filename
    
    # CRITICAL: Verify the resolved path is within UPLOAD_DIR (defense in depth)
    try:
        resolved_path = file_path.resolve()
        resolved_upload_dir = UPLOAD_DIR.resolve()
        if not str(resolved_path).startswith(str(resolved_upload_dir)):
            logger.error(f"Path traversal attempt detected: {filename} -> {file_path}")
            return {
                "success": False,
                "error": "Invalid filename",
            }
    except (OSError, ValueError):
        return {
            "success": False,
            "error": "Invalid filename",
        }

    try:
        # Save file
        file_path.write_bytes(content)

        # Extract text
        text_content = await extract_text(content, filename, force_ocr=force_ocr)

        # Background: index for semantic retrieval if enabled
        if file_id and text_content and len(text_content) > 0:
            try:
                from reasoner.core.settings import settings
                if settings.DOCUMENT_SEMANTIC_RETRIEVAL_ENABLED:
                    from reasoner.documents.vector_store import DocumentVectorStore
                    store = DocumentVectorStore()
                    task = asyncio.create_task(store.index_file(file_id, text_content))
                    _BACKGROUND_TASKS.add(task)
                    task.add_done_callback(_BACKGROUND_TASKS.discard)
                    task.add_done_callback(
                        lambda t: logger.warning(
                            "Background document indexing failed for %s: %s",
                            file_id,
                            t.exception(),
                        )
                        if not t.cancelled() and t.exception()
                        else None
                    )
            except Exception as e:
                logger.warning("Background document indexing setup failed for %s: %s", file_id, e)

        # Detect mime type for the response
        mime_type = {
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }.get(ext, "application/octet-stream")

        # Persist ownership metadata
        meta_path = UPLOAD_DIR / f"{file_id}.meta.json"
        meta_path.write_text(
            json.dumps({"user_id": user_id, "filename": filename, "mime_type": mime_type, "created_at": str(uuid.uuid4())}),
            encoding="utf-8",
        )

        # Update content-hash index
        hash_index[content_hash] = file_id
        _save_hash_index(hash_index)

        return {
            "success": True,
            "file_id": file_id,
            "filename": filename,
            "size": len(content),
            "mime_type": mime_type,
            "text": text_content,
            "path": str(file_path),
            "user_id": user_id,
        }

    except Exception as e:
        logger.error(f"File upload failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


def _get_upload_meta(file_id: str) -> dict | None:
    """Read upload metadata if it exists."""
    meta_path = UPLOAD_DIR / f"{file_id}.meta.json"
    if meta_path.exists():
        import json
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    return None


async def get_file_text(file_id: str, user_id: str | None = None) -> Optional[str]:
    """
    Retrieve extracted text from a previously uploaded file.
    
    Args:
        file_id: The file ID returned from save_uploaded_file
        user_id: If provided, enforce ownership check
        
    Returns:
        Extracted text content or None if not found or not authorized
    """
    # Validate file_id to prevent glob injection (e.g., empty string -> '*', '*' -> '**')
    if not file_id or not re.match(r'^[a-f0-9-]+$', file_id):
        return None
    
    # Ownership check
    if user_id is not None:
        meta = _get_upload_meta(file_id)
        if meta is None or meta.get("user_id") != user_id:
            return None
    
    # Look for exact file by known extensions instead of globbing
    for ext in SUPPORTED_EXTENSIONS:
        f = UPLOAD_DIR / f"{file_id}{ext}"
        if f.exists():
            try:
                content = f.read_bytes()
                return await extract_text(content, f"upload{ext}")
            except Exception as e:
                logger.error(f"Failed to retrieve file {file_id}: {e}")
                return None
    return None


def delete_file(file_id: str, user_id: str | None = None) -> bool:
    """
    Delete an uploaded file and its vector sidecar.

    Args:
        file_id: The file ID to delete
        user_id: If provided, enforce ownership check

    Returns:
        True if deleted, False if not found or not authorized
    """
    # Validate file_id to prevent glob injection
    if not file_id or not re.match(r'^[a-f0-9-]+$', file_id):
        return False

    # Ownership check
    if user_id is not None:
        meta = _get_upload_meta(file_id)
        if meta is None or meta.get("user_id") != user_id:
            return False

    deleted = False
    # Look for exact file by known extensions instead of globbing
    for ext in SUPPORTED_EXTENSIONS:
        f = UPLOAD_DIR / f"{file_id}{ext}"
        if f.exists():
            try:
                f.unlink()
                deleted = True
            except Exception as e:
                logger.error(f"Failed to delete file {file_id}: {e}")

    # Clean up metadata sidecar
    meta_path = UPLOAD_DIR / f"{file_id}.meta.json"
    if meta_path.exists():
        try:
            meta_path.unlink()
        except Exception as e:
            logger.warning(f"Failed to delete metadata for {file_id}: {e}")

    # Clean up vector sidecar if present
    if deleted:
        try:
            from reasoner.documents.vector_store import DocumentVectorStore
            store = DocumentVectorStore()
            store.delete_index(file_id)
        except Exception as e:
            logger.warning(f"Failed to delete vector sidecar for {file_id}: {e}")

    return deleted


def list_uploads(user_id: str | None = None) -> list[dict[str, Any]]:
    """
    List uploaded files.
    
    Args:
        user_id: If provided, filter to this user's uploads
        
    Returns:
        List of file info dictionaries
    """
    files = []
    for f in UPLOAD_DIR.iterdir():
        if not f.is_file() or f.suffix == ".json":
            continue
        file_id = f.stem[:12]
        meta = _get_upload_meta(file_id)
        if user_id is not None and (meta is None or meta.get("user_id") != user_id):
            continue
        stat = f.stat()
        files.append({
            "file_id": file_id,
            "filename": meta.get("filename", f.name[12:]) if meta else f.name[12:],
            "size": stat.st_size,
            "created": stat.st_ctime,
        })
    return sorted(files, key=lambda x: x["created"], reverse=True)
