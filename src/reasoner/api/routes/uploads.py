"""File upload endpoints."""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from reasoner.api.auth_deps import require_csrf
from reasoner.api.dependencies import check_rate_limit, get_current_user, require_key_scope
from reasoner.core.constants_limits import UPLOAD_USER_QUOTA_BYTES
from reasoner.core.settings import settings
from reasoner.domain.saas import User
from reasoner.infrastructure.persistence.upload_usage_repo import get_upload_usage_repo
from reasoner.uploader import (
    MAX_FILE_SIZE,
    delete_file,
    file_stored_bytes,
    get_file_text,
    list_uploads,
    save_uploaded_file,
    save_uploaded_files,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/upload")
async def upload_file(
    request: Request,
    force_ocr: bool = Query(False, description="Use OCR for images and scanned PDFs"),
    user: User = Depends(require_key_scope("write")),
    rate_limit_checked=Depends(check_rate_limit),
    csrf_checked=Depends(require_csrf),
):
    """Upload one or more files and extract their text content."""
    try:
        # Reject oversized multipart bodies before Starlette parses them into
        # memory/tempfiles.  Per-file streaming checks below remain required
        # because Content-Length may be absent or intentionally misleading.
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                request_limit = (MAX_FILE_SIZE * settings.UPLOAD_MAX_FILES) + (1024 * 1024)
                if int(content_length) > request_limit:
                    raise HTTPException(status_code=413, detail="Upload request is too large")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid Content-Length header") from None

        form = await request.form()
        files = []

        # FastAPI/Uvicorn sends multiple files with the same key as a list or single item
        raw_files = form.getlist("file") if hasattr(form, "getlist") else form.multi_items()
        if not raw_files:
            # Fallback for single file
            single = form.get("file")
            if single:
                raw_files = [single]

        if not raw_files:
            return {"success": False, "error": "No file provided"}

        if len(raw_files) > settings.UPLOAD_MAX_FILES:
            raise HTTPException(
                status_code=413,
                detail=f"Too many files. Maximum: {settings.UPLOAD_MAX_FILES}",
            )

        # Normalize to list of (bytes, filename) tuples — stream read with size guard
        for item in raw_files:
            if hasattr(item, "read"):
                chunks = []
                total = 0
                while True:
                    chunk = await item.read(1024 * 1024)  # 1 MB chunks
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_FILE_SIZE:
                        raise HTTPException(
                            status_code=413,
                            detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024 * 1024)}MB",
                        )
                    chunks.append(chunk)
                content = b"".join(chunks)
                files.append((content, getattr(item, "filename", "unknown")))

        # Reserve before writing, in one atomic step (PER-8): a check against
        # a sum read earlier let parallel uploads all pass it.
        user_id = str(user.id)
        usage = get_upload_usage_repo()
        incoming = sum(len(content) for content, _ in files)
        if not await usage.reserve(user_id, incoming, UPLOAD_USER_QUOTA_BYTES):
            raise HTTPException(
                status_code=413,
                detail=f"Upload quota of {UPLOAD_USER_QUOTA_BYTES // 2**20}MB per user exceeded",
            )
        results: list[dict] = []
        try:
            if len(files) == 1:
                results = [await save_uploaded_file(files[0][0], files[0][1], user_id=user_id, force_ocr=force_ocr)]
            else:
                results = await save_uploaded_files(files, user_id=user_id, force_ocr=force_ocr)
        finally:
            # Settle to what is really on disk: ciphertext and the text
            # sidecar, nothing for a failed or deduplicated file. The
            # reservation was the plaintext size, so one upload can overshoot
            # the cap by its own encryption overhead; the next one is refused.
            stored = sum(r.get("stored_bytes", 0) for r in results if r.get("success"))
            await usage.adjust(user_id, stored - incoming)
        return {"success": True, "files": results}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        return {"success": False, "error": "Internal server error"}


@router.get("/api/uploads")
async def get_uploads(
    user: User = Depends(get_current_user),
    rate_limit_checked=Depends(check_rate_limit),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List uploaded files for the current user with pagination."""
    all_files = list_uploads(user_id=str(user.id))
    return {"files": all_files[offset:offset + limit], "total": len(all_files)}


@router.get("/api/upload/{file_id}")
async def get_uploaded_file(
    file_id: str,
    user: User = Depends(get_current_user),
    rate_limit_checked=Depends(check_rate_limit),
):
    """Get text content of an uploaded file."""
    text = await get_file_text(file_id, user_id=str(user.id))
    if text is None:
        raise HTTPException(status_code=404, detail="File not found")
    return {"file_id": file_id, "text": text}


@router.delete("/api/upload/{file_id}")
async def delete_uploaded_file(
    file_id: str,
    user: User = Depends(require_key_scope("write")),
    rate_limit_checked=Depends(check_rate_limit),
):
    """Delete an uploaded file."""
    size = file_stored_bytes(file_id) if re.fullmatch(r"[a-f0-9-]+", file_id) else 0
    success = delete_file(file_id, user_id=str(user.id))
    if not success:
        raise HTTPException(status_code=404, detail="File not found")
    await get_upload_usage_repo().adjust(str(user.id), -size)
    return {"status": "deleted"}
