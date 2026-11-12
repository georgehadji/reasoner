"""File upload endpoints."""

from __future__ import annotations

import asyncio
import logging
import re

import anyio
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from reasoner.api.auth_deps import require_csrf
from reasoner.api.dependencies import check_rate_limit, require_key_scope
from reasoner.core.constants_limits import SETTLE_TIMEOUT_SECONDS, UPLOAD_USER_QUOTA_BYTES
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
    user_id = str(user.id)
    usage = get_upload_usage_repo()
    reserved = 0  # total bytes reserved against the quota
    consumed = 0  # plaintext bytes of files read so far
    stored = 0
    try:
        # Reject oversized multipart bodies before Starlette parses them into
        # memory/tempfiles.  Per-file streaming checks below remain required
        # because Content-Length may be absent or intentionally misleading.
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                request_limit = (MAX_FILE_SIZE * settings.UPLOAD_MAX_FILES) + (1024 * 1024)
                declared = int(content_length)
                if declared > request_limit:
                    raise HTTPException(status_code=413, detail="Upload request is too large")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid Content-Length header") from None

            # Reserve before reading any file (PER-8: atomic, so parallel
            # uploads cannot all pass a stale check). The declared body size
            # over-counts multipart framing slightly; settled below. When that
            # framing alone tips it over the cap, fall back to per-file
            # reservation, but refuse a user already at quota without reading.
            if await usage.reserve(user_id, max(declared, 0), UPLOAD_USER_QUOTA_BYTES):
                reserved = max(declared, 0)
            elif await usage.get(user_id) >= UPLOAD_USER_QUOTA_BYTES:
                await _reserve_quota(usage, user_id, 1)

        form = await request.form()

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

        # One file in memory at a time: read (size-guarded), save, drop.
        results: list[dict] = []
        for item in raw_files:
            if not hasattr(item, "read"):
                continue
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
            del chunks

            # No/understated Content-Length: reserve the shortfall now.
            consumed += total
            if consumed > reserved:
                await _reserve_quota(usage, user_id, consumed - reserved)
                reserved = consumed
            results.append(
                await save_uploaded_file(
                    content, getattr(item, "filename", "unknown"), user_id=user_id, force_ocr=force_ocr
                )
            )
            stored += results[-1].get("stored_bytes", 0) if results[-1].get("success") else 0
            del content
        return {"success": True, "files": results}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e
    finally:
        # Settle to what is really on disk: ciphertext and the text sidecar,
        # nothing for a failed or deduplicated file; any unconsumed
        # reservation (early exit, framing overhead) is released. The
        # reservation was the plaintext size, so one upload can overshoot
        # the cap by its own encryption overhead; the next one is refused.
        # Shielded: a client disconnect cancels this task and the scope re-raises
        # at every await, which skipped the settle and leaked the reservation (SM-M8).
        if reserved:
            with anyio.CancelScope(shield=True), anyio.move_on_after(SETTLE_TIMEOUT_SECONDS):
                await usage.adjust(user_id, stored - reserved)


async def _reserve_quota(usage, user_id: str, nbytes: int) -> None:
    if not await usage.reserve(user_id, nbytes, UPLOAD_USER_QUOTA_BYTES):
        raise HTTPException(
            status_code=413,
            detail=f"Upload quota of {UPLOAD_USER_QUOTA_BYTES // 2**20}MB per user exceeded",
        )


@router.get("/api/uploads")
async def get_uploads(
    user: User = Depends(require_key_scope("read")),
    rate_limit_checked=Depends(check_rate_limit),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List uploaded files for the current user with pagination."""
    # shortcut: list_uploads reads one meta.json per file of every user, so cost grows
    # with the whole folder. Off the event loop for now; move to a per-user index
    # when the folder passes ~10k files.
    all_files = await asyncio.to_thread(list_uploads, user_id=str(user.id))
    return {"files": all_files[offset:offset + limit], "total": len(all_files)}


@router.get("/api/upload/{file_id}")
async def get_uploaded_file(
    file_id: str,
    user: User = Depends(require_key_scope("read")),
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
    # delete_file takes a file lock on the shared hash index: a worker thread, not the loop.
    size = 0
    if re.fullmatch(r"[a-f0-9-]+", file_id):
        size = await asyncio.to_thread(file_stored_bytes, file_id)
    success = await asyncio.to_thread(delete_file, file_id, user_id=str(user.id))
    if not success:
        raise HTTPException(status_code=404, detail="File not found")
    with anyio.CancelScope(shield=True), anyio.move_on_after(SETTLE_TIMEOUT_SECONDS):
        await get_upload_usage_repo().adjust(str(user.id), -size)
    return {"status": "deleted"}
