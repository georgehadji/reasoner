"""
Neuro Compression Module
Optimizes text context for LLM efficiency.
Uses "Neuro-Squeeze" logic for smart token reduction.
"""

import re
from enum import Enum


class CompressionLevel(Enum):
    NONE = "none"
    MINIMAL = "minimal"     # Removes comments and whitespace
    AGGRESSIVE = "aggressive"  # Keeps only structural signatures

class Language(Enum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    RUST = "rust"
    GO = "go"
    SHELL = "shell"
    UNKNOWN = "unknown"

    @classmethod
    def from_extension(cls, ext: str) -> "Language":
        ext = ext.lower().strip(".")
        mapping = {
            "py": cls.PYTHON,
            "js": cls.JAVASCRIPT, "mjs": cls.JAVASCRIPT,
            "ts": cls.TYPESCRIPT, "tsx": cls.TYPESCRIPT,
            "rs": cls.RUST,
            "go": cls.GO,
            "sh": cls.SHELL, "bash": cls.SHELL
        }
        return mapping.get(ext, cls.UNKNOWN)

class ContextCompressor:
    def __init__(self, level: CompressionLevel = CompressionLevel.MINIMAL):
        self.level = level

        # Core patterns for Neuro-Squeeze
        self.import_pattern = re.compile(r"^(use |import |from |require\(|#include)")
        self.func_signature = re.compile(
            r"^(pub\s+)?(async\s+)?(fn|def|function|func|class|struct|enum|trait|interface|type)\s+\w+"
        )
        self.blank_lines = re.compile(r"\n{3,}")

    def compress(self, content: str, language: Language = Language.UNKNOWN) -> str:
        if self.level == CompressionLevel.NONE:
            return content

        if self.level == CompressionLevel.AGGRESSIVE:
            return self._compress_aggressive(content, language)

        return self._compress_minimal(content, language)

    def _get_comment_patterns(self, lang: Language):
        # Line comments
        if lang in [Language.PYTHON, Language.SHELL]:
            return "#", None, None
        if lang in [Language.RUST, Language.JAVASCRIPT, Language.TYPESCRIPT, Language.GO]:
            return "//", "/*", "*/"
        return "//", "/*", "*/"

    def _compress_minimal(self, content: str, lang: Language) -> str:
        line_comment, block_start, block_end = self._get_comment_patterns(lang)
        result = []
        in_block = False

        for line in content.splitlines():
            trimmed = line.strip()

            # Simple block comment skip
            if block_start and block_start in trimmed:
                in_block = True
            if in_block:
                if block_end and block_end in trimmed:
                    in_block = False
                continue

            # Line comment skip (don't skip docstrings in Python)
            if line_comment and trimmed.startswith(line_comment):
                continue

            if not trimmed:
                result.append("")
                continue

            result.append(line)

        compressed = "\n".join(result)
        # Normalize blank lines
        compressed = self.blank_lines.sub("\n\n", compressed)
        return compressed.strip()

    def _compress_aggressive(self, content: str, lang: Language) -> str:
        # First do minimal to clean up
        minimal = self._compress_minimal(content, lang)
        result = []
        brace_depth = 0
        in_body = False

        for line in minimal.splitlines():
            trimmed = line.strip()

            # Keep imports
            if self.import_pattern.match(trimmed):
                result.append(line)
                continue

            # Keep signatures
            if self.func_signature.match(trimmed):
                result.append(line)
                in_body = True
                brace_depth = 0
                continue

            if in_body:
                # Track braces (naive but effective for most C-style and Python indents)
                brace_depth += trimmed.count("{")
                brace_depth -= trimmed.count("}")

                # For Python, we'd look at indentation, but here we just keep the signature
                # and a placeholder if it's a block
                if brace_depth <= 0:
                    if lang != Language.PYTHON:
                        if "{" in result[-1] and "}" not in line:
                           result.append("    // ... implementation")
                           result.append("}")
                    else:
                        result.append("    # ... implementation")
                    in_body = False
                continue

            # Keep constants/types
            if any(trimmed.startswith(x) for x in ["const ", "static ", "let ", "class ", "type "]):
                result.append(line)

        return "\n".join(result).strip()

def smart_compress(text: str, ext: str = "", level: str = "minimal") -> str:
    """Convenience helper for quick compression."""
    lvl = CompressionLevel(level)
    lang = Language.from_extension(ext)
    compressor = ContextCompressor(lvl)
    return compressor.compress(text, lang)
