"""AST-based code safety guard for the execution sandbox (#1).

Tiers:
  SAFE — passes all checks, safe to execute
  SUSPICIOUS — unusual patterns (eval, exec) but may be legitimate
  DANGEROUS — contains dangerous calls (open, subprocess, __import__)
  BLOCKED — definitely malicious (os.system, socket, import blocking)

Rejects code that attempts to:
  - Import modules outside the allowlist (EXEC_IMPORT_ALLOWLIST)
  - Call __import__(), exec(), eval(), compile()
  - Open files for writing
  - Access __builtins__ or __globals__
"""

from __future__ import annotations

import ast
import logging

from reasoner.core.exec_constants import (
    EXEC_IMPORT_ALLOWLIST,
    SAFETY_BLOCKED,
    SAFETY_DANGEROUS,
    SAFETY_SAFE,
    SAFETY_SUSPICIOUS,
)

logger = logging.getLogger(__name__)


class CodeSafetyError(Exception):
    """Raised when code is blocked by the safety guard."""


def check_code_safety(code: str) -> str:
    """Check code safety and return the safety tier.

    Args:
        code: Source code to check.

    Returns:
        One of SAFETY_SAFE, SAFETY_SUSPICIOUS, SAFETY_DANGEROUS, SAFETY_BLOCKED.

    Raises:
        CodeSafetyError: If the code is BLOCKED (cannot be executed).
    """
    if not code.strip():
        return SAFETY_SAFE

    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        # Syntax errors are caught by the executor at runtime;
        # they are not a safety concern.
        logger.debug("Code has syntax error: %s", exc)
        return SAFETY_SAFE

    tier = SAFETY_SAFE
    for node in ast.walk(tree):
        node_tier = _check_node(node)
        tier = _max_tier(tier, node_tier)

    if tier == SAFETY_BLOCKED:
        raise CodeSafetyError("Code blocked: contains prohibited constructs")

    return tier


def _max_tier(a: str, b: str) -> str:
    """Return the more restrictive tier."""
    order = {SAFETY_SAFE: 0, SAFETY_SUSPICIOUS: 1, SAFETY_DANGEROUS: 2, SAFETY_BLOCKED: 3}
    return a if order.get(a, 0) >= order.get(b, 0) else b


def _check_node(node: ast.AST) -> str:
    """Check a single AST node and return its safety tier."""
    # ── BLOCKED: OS interaction, networking, subprocess ──
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            name = node.func.id
            if name in (
                "__import__", "exec", "eval", "compile",
                "open", "input",
            ):
                return SAFETY_BLOCKED
        if isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            if attr in ("system", "popen", "Popen", "run", "call", "check_call",
                        "check_output", "fork", "execve", "spawn"):
                return SAFETY_BLOCKED

    # ── DANGEROUS: imports outside allowlist ──
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name not in EXEC_IMPORT_ALLOWLIST:
                # Allow 'import X.Y.Z' where X is in the allowlist
                top_level = alias.name.split(".")[0]
                if top_level not in EXEC_IMPORT_ALLOWLIST:
                    logger.debug("Blocked import: %s", alias.name)
                    return SAFETY_BLOCKED

    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        top_level = module.split(".")[0]
        if top_level and top_level not in EXEC_IMPORT_ALLOWLIST:
            logger.debug("Blocked from-import: %s", module)
            return SAFETY_BLOCKED

    # ── BLOCKED: deserialization and file-like access by attribute ──
    # This is defense in depth only.  The real security boundary must be an
    # isolated execution service, not this AST inspection.
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr in {
            "loads", "load", "read_text", "read_bytes", "write_text",
            "write_bytes", "open", "unlink", "rename", "replace",
        }:
            return SAFETY_BLOCKED

    # ── SUSPICIOUS: eval/exec via attribute access ──
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute):
            if node.func.attr in ("eval", "exec", "compile"):
                return SAFETY_SUSPICIOUS

    # ── DANGEROUS: __builtins__ / __globals__ access ──
    if isinstance(node, ast.Name):
        if node.id in ("__builtins__", "__globals__", "__locals__"):
            return SAFETY_BLOCKED

    # ── DANGEROUS: Try/except with bare except (swallows everything) ──
    if isinstance(node, ast.ExceptHandler):
        if node.type is None:
            return SAFETY_SUSPICIOUS

    return SAFETY_SAFE
