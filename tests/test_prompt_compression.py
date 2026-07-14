"""Tests for prompt code-block compression in LLMExecutor."""

from __future__ import annotations

import pytest

from reasoner.infrastructure.llm.executor import LLMExecutor


class TestCompressPromptCodeBlocks:
    """Unit tests for _compress_prompt_code_blocks static method."""

    def test_no_code_blocks_unchanged(self):
        prompt = "Explain quantum computing in simple terms."
        result = LLMExecutor._compress_prompt_code_blocks(prompt, "primary")
        assert result == prompt

    def test_python_code_block_compressed(self):
        prompt = '''Here is some code:
```python
# This is a comment
import os

def hello():
    """Docstring"""
    print("hello")


# Another comment
x = 1
```
What does it do?
'''
        result = LLMExecutor._compress_prompt_code_blocks(prompt, "coding_spec")
        # Comments should be stripped
        assert "# This is a comment" not in result
        assert "# Another comment" not in result
        # Code should remain
        assert "import os" in result
        assert "def hello():" in result
        assert "print(\"hello\")" in result

    def test_non_code_role_skips_compression(self):
        prompt = '''```python
# comment
x = 1
```'''
        result = LLMExecutor._compress_prompt_code_blocks(prompt, "synthesis")
        # synthesis is not in code_heavy_roles
        assert "# comment" in result

    def test_multiple_code_blocks(self):
        prompt = '''```python
# comment 1
x = 1
```
Some text
```javascript
// js comment
const y = 2;
```'''
        result = LLMExecutor._compress_prompt_code_blocks(prompt, "coding_generate")
        assert "# comment 1" not in result
        assert "// js comment" not in result
        assert "x = 1" in result
        assert "const y = 2;" in result

    def test_unknown_language_defaults_to_minimal(self):
        prompt = '''```rust
// rust comment
fn main() {}
```'''
        result = LLMExecutor._compress_prompt_code_blocks(prompt, "coding_review")
        assert "// rust comment" not in result
        assert "fn main()" in result
