"""Regression tests for HTTPException swallowing bugs in API routes."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROUTES_DIR = Path(__file__).parent.parent / "src" / "reasoner" / "api" / "routes"


def _find_http_exception_swallowing(filepath: Path) -> list[int]:
    """Parse a Python file and find bare/except-Exception blocks that swallow HTTPException.

    We look for `try` blocks where:
    1. An `HTTPException` is raised inside the try body
    2. The corresponding `except` clause catches `Exception` (or bare `except`) WITHOUT
       a preceding `except HTTPException: raise` handler.
    """
    src = filepath.read_text(encoding="utf-8")
    tree = ast.parse(src)
    violations = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue

        # Check if HTTPException is raised anywhere in the try body
        has_http_raise = False
        for stmt in ast.walk(ast.Module(body=node.body, type_ignores=[])):
            if isinstance(stmt, ast.Raise):
                exc = stmt.exc
                if isinstance(exc, ast.Call):
                    if isinstance(exc.func, ast.Name) and exc.func.id == "HTTPException":
                        has_http_raise = True
                    elif (
                        isinstance(exc.func, ast.Attribute)
                        and exc.func.attr == "HTTPException"
                    ):
                        has_http_raise = True

        if not has_http_raise:
            continue

        # Check handlers in order. If we see `except HTTPException: raise` first,
        # then subsequent broad handlers are safe.
        http_re_raise_seen = False
        for handler in node.handlers:
            # Is this an HTTPException handler with re-raise?
            is_http_handler = False
            if handler.type is not None:
                if isinstance(handler.type, ast.Name) and handler.type.id == "HTTPException":
                    is_http_handler = True
                elif isinstance(handler.type, ast.Tuple):
                    for elt in handler.type.elts:
                        if isinstance(elt, ast.Name) and elt.id == "HTTPException":
                            is_http_handler = True

            if is_http_handler:
                for stmt in ast.walk(ast.Module(body=handler.body, type_ignores=[])):
                    if isinstance(stmt, ast.Raise):
                        http_re_raise_seen = True
                        break
                continue

            # Is this a broad handler?
            catches_broad = False
            if handler.type is None:  # bare except
                catches_broad = True
            elif isinstance(handler.type, ast.Name) and handler.type.id == "Exception":
                catches_broad = True
            elif isinstance(handler.type, ast.Tuple):
                for elt in handler.type.elts:
                    if isinstance(elt, ast.Name) and elt.id == "Exception":
                        catches_broad = True

            if catches_broad and not http_re_raise_seen:
                violations.append(handler.lineno or node.lineno)

    return violations


class TestUploadsHTTPException:
    """BUG-001: uploads.py must not swallow HTTPException(413) for oversized files."""

    def test_no_http_exception_swallowing(self):
        violations = _find_http_exception_swallowing(ROUTES_DIR / "uploads.py")
        assert not violations, (
            f"uploads.py has except-Exception block(s) that swallow HTTPException "
            f"at line(s): {violations}. Add `except HTTPException: raise` before the broad handler."
        )


class TestContextHTTPException:
    """BUG-002: context.py must not swallow HTTPException(403) for unsafe URLs."""

    def test_no_http_exception_swallowing(self):
        violations = _find_http_exception_swallowing(ROUTES_DIR / "context.py")
        assert not violations, (
            f"context.py has except-Exception block(s) that swallow HTTPException "
            f"at line(s): {violations}. Add `except HTTPException: raise` before the broad handler."
        )


class TestAuthDepsNoPrint:
    """BUG-003: auth_deps.py must not contain debug print statements."""

    def test_no_print_statements(self):
        auth_deps_path = (
            Path(__file__).parent.parent
            / "src"
            / "reasoner"
            / "api"
            / "auth_deps.py"
        )
        src = auth_deps_path.read_text(encoding="utf-8")
        tree = ast.parse(src)

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "print":
                    pytest.fail(
                        f"Unexpected print() call found in auth_deps.py at line {node.lineno}"
                    )


class TestPipelinesHTTPException:
    """BUG-004: pipelines.py must not swallow HTTPException in any route handler."""

    def test_no_http_exception_swallowing(self):
        violations = _find_http_exception_swallowing(ROUTES_DIR / "pipelines.py")
        assert not violations, (
            f"pipelines.py has except-Exception block(s) that swallow HTTPException "
            f"at line(s): {violations}. Add `except HTTPException: raise` before the broad handler."
        )


class TestImagesHTTPException:
    """BUG-005: images.py must not swallow HTTPException(429) from quota checks."""

    def test_no_http_exception_swallowing(self):
        violations = _find_http_exception_swallowing(ROUTES_DIR / "images.py")
        assert not violations, (
            f"images.py has except-Exception block(s) that swallow HTTPException "
            f"at line(s): {violations}. Add `except HTTPException: raise` before the broad handler."
        )


class TestLegacyWidgetsHTTPException:
    """BUG-006: legacy_widgets.py calculate() must not swallow HTTPException."""

    def test_calculate_no_http_exception_swallowing(self):
        violations = _find_http_exception_swallowing(ROUTES_DIR / "legacy_widgets.py")
        assert not violations, (
            f"legacy_widgets.py has except-Exception block(s) that swallow HTTPException "
            f"at line(s): {violations}. Add `except HTTPException: raise` before the broad handler."
        )
