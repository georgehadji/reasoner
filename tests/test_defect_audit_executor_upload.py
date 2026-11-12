"""Defect audit: multi-line sandbox code and upload error text.

D1: SubprocessExecutor wrapped f"...{code}" in textwrap.dedent, so any code with a
    line at column 0 left the header lines indented and the script died with
    IndentationError.
D2: save_uploaded_file returned str(e) to the client, which carries server paths.
"""

from __future__ import annotations

import pytest

from reasoner.core.settings import settings
from reasoner.infrastructure import uploader
from reasoner.infrastructure.execution.subprocess_executor import SubprocessExecutor

pytestmark = pytest.mark.unit


async def test_multi_line_code_runs():
    """Violated property: valid multi-line Python runs as written."""
    result = await SubprocessExecutor().execute("x = 2\ny = 3\nprint(x * y)")

    assert result.success, result.stderr
    assert result.stdout.strip() == "6"


async def test_a_function_definition_runs():
    code = "def f(a):\n    return a + 1\nprint(f(1))"

    result = await SubprocessExecutor().execute(code)

    assert result.success, result.stderr
    assert result.stdout.strip() == "2"


async def test_upload_failure_does_not_leak_exception_text(tmp_path, monkeypatch):
    """Violated property: client-visible errors carry no server paths."""
    import reasoner.documents.vector_store as vector_store_module

    monkeypatch.setattr(uploader, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(vector_store_module, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(uploader, "_MAGIC_AVAILABLE", False)
    monkeypatch.setattr(settings, "UPLOAD_REQUIRE_MIME_VALIDATION", False)
    monkeypatch.setattr(settings, "DOCUMENT_SEMANTIC_RETRIEVAL_ENABLED", False)

    async def _boom(*_a, **_k):
        raise OSError(2, "No such file or directory", str(tmp_path / "secret.bin"))

    monkeypatch.setattr(uploader, "extract_text", _boom)

    result = await uploader.save_uploaded_file(b"data", "a.txt", user_id="u")

    assert result["success"] is False
    assert str(tmp_path) not in result["error"]
    assert "secret.bin" not in result["error"]
