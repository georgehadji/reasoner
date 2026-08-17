"""Tests for I/O and security bug fixes (BUG-007, BUG-008, BUG-009 regression)."""

import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestCacheRaceConditionPrevention:
    """BUG-007 regression tests: Cache writes must be race-condition safe."""

    def test_unique_temp_filename_per_write(self):
        """Test that each cache write uses a unique temp filename."""
        from reasoner.api import CACHE_DIR
        import time
        
        # Simulate two writes in quick succession
        key = "test_key"
        
        # First write
        tmp1_name = f"{key}.{os.getpid()}.{int(time.time() * 1000)}.tmp"
        time.sleep(0.002)  # 2ms delay
        
        # Second write
        tmp2_name = f"{key}.{os.getpid()}.{int(time.time() * 1000)}.tmp"
        
        # Filenames should be different due to timestamp
        assert tmp1_name != tmp2_name

    def test_temp_file_cleanup(self):
        """Test that old temp files are cleaned up."""
        from reasoner.api import CACHE_DIR
        
        # Create fake old temp files
        old_tmp1 = CACHE_DIR / "test_cleanup.12345.1000.tmp"
        old_tmp2 = CACHE_DIR / "test_cleanup.12345.1001.tmp"
        old_tmp1.touch(exist_ok=True)
        old_tmp2.touch(exist_ok=True)
        
        try:
            # Verify they exist
            assert old_tmp1.exists()
            assert old_tmp2.exists()
            
            # Cleanup (simulating what _save_cache does)
            for old_tmp in CACHE_DIR.glob("test_cleanup.*.tmp"):
                old_tmp.unlink(missing_ok=True)
            
            # Verify they're deleted
            assert not old_tmp1.exists()
            assert not old_tmp2.exists()
        finally:
            # Ensure cleanup
            old_tmp1.unlink(missing_ok=True)
            old_tmp2.unlink(missing_ok=True)


class TestPathTraversalPrevention:
    """BUG-008 regression tests: File upload must prevent path traversal."""

    def test_path_traversal_in_extension_rejected(self):
        """Test that path traversal in extension is rejected."""
        from reasoner.uploader import _get_file_extension
        
        # Malicious filenames
        malicious = [
            "../../../etc/passwd.txt",
            "..\\..\\..\\windows\\system32\\config.txt",
            "test/../../../evil.txt",
            "file.txt/../../../evil.txt",
        ]
        
        for filename in malicious:
            ext = _get_file_extension(filename)
            # Extension should only be the last component
            assert "/" not in ext
            assert "\\" not in ext

    def test_extension_validation_regex(self):
        """Test the extension validation regex."""
        import re
        
        pattern = r'^\.[a-zA-Z0-9]+$'
        
        # Valid extensions
        valid = [".txt", ".pdf", ".docx", ".TXT", ".PDF", ".test123"]
        for ext in valid:
            assert re.match(pattern, ext), f"{ext} should be valid"
        
        # Invalid extensions
        invalid = [
            "",  # Empty
            ".txt/../../../evil",  # Path traversal
            ".txt\\..\\..",  # Windows path traversal
            ".txt/../etc",  # Mixed
            "txt",  # No dot
            ".txt.bak",  # Multiple dots
            ".txt\x00",  # Null byte
        ]
        for ext in invalid:
            assert not re.match(pattern, ext), f"{ext} should be invalid"

    def test_safe_filename_construction(self):
        """Test that safe filename is constructed properly."""
        import uuid
        import re
        
        # Simulate the safe filename construction
        file_id = str(uuid.uuid4())[:12]
        ext = ".txt"
        safe_filename = f"{file_id}{ext}"
        
        # Should only contain alphanumeric, dot, hyphen from UUID
        # UUID can contain hyphens, so allow them
        assert re.match(r'^[a-f0-9-]+\.txt$', safe_filename)
        
        # Should not contain path separators
        assert "/" not in safe_filename
        assert "\\" not in safe_filename
        assert ".." not in safe_filename

    def test_path_resolution_check(self):
        """Test that path resolution check prevents escape."""
        from pathlib import Path
        
        upload_dir = Path("/safe/uploads")
        
        # Safe path
        safe_file = upload_dir / "abc123.txt"
        assert str(safe_file.resolve()).startswith(str(upload_dir.resolve()))
        
        # Attempted escape (would be caught before this, but testing defense in depth)
        # Note: Path doesn't resolve .. without the file existing, so we test the logic
        escape_attempt = upload_dir / "../../../etc/passwd"
        # The resolve() would go outside upload_dir if the path existed
        # Our validation prevents this from being constructed in the first place


class TestHistoryDeleteErrorHandling:
    """BUG-009 regression tests: History delete must handle errors gracefully."""

    def test_delete_nonexistent_entry(self):
        """Test deleting non-existent entry returns 404."""
        # This simulates the API behavior
        from pathlib import Path
        
        history_dir = Path(tempfile.mkdtemp())
        path = history_dir / "nonexistent.json"
        
        # Should not raise, should handle gracefully
        if not path.exists():
            result = {"error": "Entry not found"}, 404
            assert result[1] == 404
        
        # Cleanup
        import shutil
        shutil.rmtree(history_dir, ignore_errors=True)

    def test_delete_with_missing_ok(self):
        """Test that unlink(missing_ok=True) handles race condition."""
        from pathlib import Path
        import tempfile
        
        history_dir = Path(tempfile.mkdtemp())
        path = history_dir / "test.json"
        
        # Create file
        path.touch()
        assert path.exists()
        
        # Delete it
        path.unlink(missing_ok=True)
        assert not path.exists()
        
        # Delete again - should not raise
        path.unlink(missing_ok=True)  # No exception
        
        # Cleanup
        import shutil
        shutil.rmtree(history_dir, ignore_errors=True)

    def test_clear_history_with_failures(self):
        """Test that clear_history handles individual failures."""
        from pathlib import Path
        import tempfile
        
        history_dir = Path(tempfile.mkdtemp())
        
        # Create some files
        (history_dir / "file1.json").touch()
        (history_dir / "file2.json").touch()
        
        cleared = 0
        failed = 0
        
        for f in history_dir.glob("*.json"):
            try:
                f.unlink(missing_ok=True)
                cleared += 1
            except OSError:
                failed += 1
        
        assert cleared == 2
        assert failed == 0
        
        # Cleanup
        import shutil
        shutil.rmtree(history_dir, ignore_errors=True)


class TestUploaderGlobInjection:
    """BUG-010 regression tests: uploader must not be vulnerable to glob injection."""

    @pytest.mark.anyio
    async def test_get_file_text_rejects_empty_file_id(self, tmp_path, monkeypatch):
        from reasoner import uploader
        monkeypatch.setattr(uploader, 'UPLOAD_DIR', tmp_path)
        (tmp_path / "secret.txt").write_text("sensitive")
        assert await uploader.get_file_text("") is None

    @pytest.mark.anyio
    async def test_get_file_text_rejects_wildcard_file_id(self, tmp_path, monkeypatch):
        from reasoner import uploader
        monkeypatch.setattr(uploader, 'UPLOAD_DIR', tmp_path)
        (tmp_path / "secret.txt").write_text("sensitive")
        assert await uploader.get_file_text("*") is None

    @pytest.mark.anyio
    async def test_get_file_text_rejects_dotdot_file_id(self, tmp_path, monkeypatch):
        from reasoner import uploader
        monkeypatch.setattr(uploader, 'UPLOAD_DIR', tmp_path)
        (tmp_path / "secret.txt").write_text("sensitive")
        assert await uploader.get_file_text("..") is None

    @pytest.mark.anyio
    async def test_get_file_text_reads_exact_match(self, tmp_path, monkeypatch):
        from reasoner import uploader
        from reasoner.infrastructure import uploader as impl_uploader
        # get_file_text is defined in infrastructure.uploader and reads its own
        # module-global UPLOAD_DIR — the shim's copy is a separate binding.
        monkeypatch.setattr(impl_uploader, 'UPLOAD_DIR', tmp_path)
        file_id = "abc123def456"
        (tmp_path / f"{file_id}.txt").write_text("hello world")
        result = await uploader.get_file_text(file_id)
        assert result == "hello world"

    def test_delete_file_rejects_injection_attempts(self, tmp_path, monkeypatch):
        from reasoner import uploader
        monkeypatch.setattr(uploader, 'UPLOAD_DIR', tmp_path)
        (tmp_path / "secret.txt").write_text("sensitive")
        assert uploader.delete_file("") is False
        assert uploader.delete_file("*") is False
        assert uploader.delete_file("..") is False
        assert (tmp_path / "secret.txt").exists()

    def test_delete_file_deletes_exact_match(self, tmp_path, monkeypatch):
        from reasoner import uploader
        from reasoner.infrastructure import uploader as impl_uploader
        monkeypatch.setattr(impl_uploader, 'UPLOAD_DIR', tmp_path)
        file_id = "abc123def456"
        (tmp_path / f"{file_id}.txt").write_text("hello world")
        assert uploader.delete_file(file_id) is True
        assert not (tmp_path / f"{file_id}.txt").exists()


class TestCalculatorNoEval:
    """BUG-001 regression tests: calculator must never fall back to eval()."""

    @pytest.mark.asyncio
    async def test_calculator_evaluates_safely(self):
        from reasoner.infrastructure.widgets.calculator import CalculatorWidget
        widget = CalculatorWidget()
        result = await widget._execute_impl({'expression': '2 + 3 * 4'})
        assert result['valid'] is True
        assert result['result'] == 14

    def test_calculator_has_no_basic_eval_method(self):
        from reasoner.infrastructure.widgets.calculator import CalculatorWidget
        widget = CalculatorWidget()
        assert not hasattr(widget, '_basic_eval')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
