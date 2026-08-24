#!/usr/bin/env python3
"""Secret scanner — detect API keys and tokens in source code.

Critical Enhancement 6.3: replaces naive grep with structured regex scanning.
Usage: python scripts/scan-secrets.py [path]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Patterns for common secrets
PATTERNS = {
    "stripe_live_key": re.compile(r"sk_live_[a-zA-Z0-9]{24,}"),
    "stripe_test_key": re.compile(r"sk_test_[a-zA-Z0-9]{24,}"),
    "jwt_bare": re.compile(r"eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*"),
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "aws_secret_key": re.compile(r"(?:AWS|aws).*?[0-9a-zA-Z/+]{40}"),
    "generic_api_key": re.compile(r"api[_-]?key\s*[:=]\s*['\"][a-zA-Z0-9_-]{16,}['\"]", re.IGNORECASE),
    "generic_secret": re.compile(r"secret\s*[:=]\s*['\"][a-zA-Z0-9_-]{16,}['\"]", re.IGNORECASE),
    "private_key": re.compile(r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,}"),
    "openai_key": re.compile(r"sk-[a-zA-Z0-9]{20,}"),
}

# Files and paths to skip
SKIP_PATHS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
    ".next", "out", "dist", "build", ".mypy_cache", ".ruff_cache",
    "docs", "tasks", "cache", "history", "uploads",
    "tests",  # test fixtures deliberately contain fake credentials
    "deepseek-harness",  # separate embedded repo, not part of this project
}

SKIP_FILES = {
    ".env", ".env.local", ".env.example", "poetry.lock", "package-lock.json",
    "yarn.lock", "pnpm-lock.yaml", "Pipfile.lock", "tsconfig.tsbuildinfo",
    "openrouter_models.json", "openrouter_models_formatted.txt",
    "autonomous_bug_fix_report.json", ".searxng-settings.yml",
}

SKIP_EXTENSIONS = {
    ".md", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2",
    ".ttf", ".eot", ".pdf", ".zip", ".tar", ".gz", ".mp4", ".mp3",
    ".db", ".sqlite", ".sqlite3",  # binary database files
}


def scan_file(path: Path) -> list[dict]:
    """Scan a single file for secrets."""
    findings = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return findings

    for name, pattern in PATTERNS.items():
        for match in pattern.finditer(text):
            # Skip if it's clearly a placeholder/example
            matched = match.group(0)
            if any(p in matched.lower() for p in ("example", "placeholder", "your_", "...", "xxx", "secret_", "_path")):
                continue
            # Skip if inside a test mock
            if "test" in path.name.lower() and "mock" in text[max(0, match.start()-50):match.start()].lower():
                continue
            findings.append({
                "file": str(path),
                "line": text[:match.start()].count("\n") + 1,
                "type": name,
                "match": matched[:40] + "..." if len(matched) > 40 else matched,
            })
    return findings


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    all_findings: list[dict] = []

    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if any(part in SKIP_PATHS for part in path.parts):
            continue
        if path.name in SKIP_FILES:
            continue
        if path.suffix in SKIP_EXTENSIONS:
            continue

        findings = scan_file(path)
        all_findings.extend(findings)

    if all_findings:
        print(f"WARNING: Found {len(all_findings)} potential secret(s):")
        for f in all_findings:
            print(f"  {f['file']}:{f['line']}  [{f['type']}]  {f['match']}")
        return 1
    else:
        print("OK: No secrets detected in source.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
