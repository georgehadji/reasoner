"""PDF/DOCX text extraction, run in a child process the caller can kill.

pypdf and python-docx parse synchronously. On the event loop, a hostile file
(a zip bomb, a pathological PDF) blocked every request, and the extraction
timeout could not interrupt it: ``wait_for`` only cancels at an ``await``.
The uploader runs this module as a script, so a timeout kills the process,
and on Linux the child caps its own address space first.

Only the stdlib and the two parsers are imported here: the child must not pay
for, or depend on, the app's settings and package imports.

Protocol: ``python parse_worker.py <pdf|docx> <memory_limit_bytes>``, file
bytes on stdin, UTF-8 text on stdout. A parse error exits non-zero with the
error as the last stderr line; the uploader logs it and turns it into the
bracketed notice it already understands.
"""

from __future__ import annotations

import io
import sys
import zipfile

# A .docx is a zip. Checked before parsing, from the central directory alone,
# so a bomb is refused without inflating anything. The directory can lie about
# sizes; the child's memory cap and the timeout are the backstop for that.
MAX_ZIP_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_ZIP_COMPRESSION_RATIO = 100


def zip_bomb_reason(content: bytes) -> str | None:
    """Why this zip must not be inflated, or None when it looks sane."""
    try:
        members = zipfile.ZipFile(io.BytesIO(content)).infolist()
    except zipfile.BadZipFile:
        return None  # not a zip: the parser reports its own error
    total = sum(m.file_size for m in members)
    if total > MAX_ZIP_UNCOMPRESSED_BYTES:
        return f"expands to {total} bytes"
    packed = sum(m.compress_size for m in members)
    if packed and total / packed > MAX_ZIP_COMPRESSION_RATIO:
        return f"compression ratio {total // packed}:1"
    return None


def parse_pdf(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return "[PDF extraction not available - install pypdf]"
    reader = PdfReader(io.BytesIO(content))
    return "\n".join(page.extract_text() for page in reader.pages)


def parse_docx(content: bytes) -> str:
    try:
        from docx import Document
    except ImportError:
        return "[DOCX extraction not available - install python-docx]"
    reason = zip_bomb_reason(content)
    if reason:
        return f"[DOCX extraction failed: refused, archive {reason}]"
    doc = Document(io.BytesIO(content))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


PARSERS = {"pdf": parse_pdf, "docx": parse_docx}


def _cap_memory(limit: int) -> None:
    try:
        import resource
    except ImportError:  # Windows: the timeout kill is the only bound
        return
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))


if __name__ == "__main__":
    kind, limit = sys.argv[1], int(sys.argv[2])
    data = sys.stdin.buffer.read()
    if limit > 0:
        _cap_memory(limit)
    sys.stdout.buffer.write(PARSERS[kind](data).encode("utf-8", errors="replace"))
