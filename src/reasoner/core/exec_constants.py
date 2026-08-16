"""Constants for the code execution sandbox (Code-as-Agent-Harness #1)."""

from __future__ import annotations

# ── Resource limits ──
EXEC_DEFAULT_TIMEOUT_MS: int = 30_000        # 30s wall-clock
EXEC_MEM_LIMIT_MB: int = 256                  # process RSS cap
EXEC_MAX_OUTPUT_BYTES: int = 65_536           # stdout/stderr clip

# ── Import allowlist (safe stdlib modules for PoT execution) ──
EXEC_IMPORT_ALLOWLIST: frozenset[str] = frozenset({
    # Core data structures
    "dataclasses", "collections", "enum", "typing",
    # Math and numbers
    "math", "decimal", "fractions", "random", "statistics",
    # Text processing
    "re", "string", "textwrap", "difflib", "unicodedata",
    # Dates
    "datetime", "calendar", "time",
    # JSON / serialisation
    "json", "base64", "binascii", "hashlib", "uuid",
    # Iteration / functional
    "itertools", "functools", "operator",
    # Copy only.  Filesystem and pickle are intentionally unavailable: the
    # executor is not a security boundary and must never deserialize or access
    # host data.  A future isolated runner may define its own allowlist.
    "copy",
    # Warnings / errors
    "warnings", "contextlib",
    # Type checking (runtime)
    "inspect",
})

# ── AST safety tiers ──
EXEC_SAFETY_DANGEROUS_KEYWORDS: frozenset[str] = frozenset({
    "import", "__import__", "exec", "eval", "compile",
    "open", "__builtins__",
})

# Tier constants
SAFETY_SAFE = "SAFE"
SAFETY_SUSPICIOUS = "SUSPICIOUS"
SAFETY_DANGEROUS = "DANGEROUS"
SAFETY_BLOCKED = "BLOCKED"
