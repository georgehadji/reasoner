"""
Patch dynamic metadata in architecture/codebase docs after each commit.

Targets:
  - ARCHITECTURE_MINDMAP.md  (root)
  - docs/CODEBASE_MINDMAP.md
  - docs/CODEMAPS/*.md       (<!-- Generated: ... --> headers)

Updates: Last Updated date, Python source file count, model count,
preset count, reasoning method count — all derived from live code.
Leaves all prose untouched.
"""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARCHITECTURE_MINDMAP = ROOT / "ARCHITECTURE_MINDMAP.md"
CODEBASE_MINDMAP = ROOT / "docs" / "CODEBASE_MINDMAP.md"
CODEMAPS_DIR = ROOT / "docs" / "CODEMAPS"


# ── Live counts ──────────────────────────────────────────────────────────────

def _count_py_files() -> int:
    src = ROOT / "src" / "reasoner"
    return len(list(src.rglob("*.py"))) if src.exists() else 0


def _count_models() -> int:
    try:
        import importlib
        sys.path.insert(0, str(ROOT / "src"))
        mod = importlib.import_module("reasoner.infrastructure.llm.registry")
        whitelist = getattr(mod, "_MODEL_WHITELIST", None)
        return len(whitelist) if whitelist else 0
    except Exception:
        return 0


def _count_presets() -> int:
    try:
        import importlib
        sys.path.insert(0, str(ROOT / "src"))
        mod = importlib.import_module("reasoner.presets")
        presets = getattr(mod, "PRESETS", None)
        return len(presets) if presets else 0
    except Exception:
        return 0


def _count_methods() -> int:
    phases_dir = ROOT / "src" / "reasoner" / "phases"
    if not phases_dir.exists():
        return 0
    return len([
        f for f in phases_dir.glob("*.py")
        if not f.stem.startswith("_") and f.stem != "__init__"
    ])


# ── Patching helpers ──────────────────────────────────────────────────────────

def _patch(text: str, pattern: str, replacement: str, label: str = "") -> str:
    new, n = re.subn(pattern, replacement, text, count=1)
    if n == 0 and label:
        print(f"  [mindmap] WARNING: pattern not found in {label} — {pattern!r}", file=sys.stderr)
    return new


def _stage(path: Path) -> None:
    subprocess.run(
        ["git", "add", str(path.relative_to(ROOT))],
        cwd=ROOT, check=False, capture_output=True,
    )


# ── Per-document updaters ────────────────────────────────────────────────────

def _update_architecture_mindmap(today: str, py: int, models: int, presets: int, methods: int) -> bool:
    if not ARCHITECTURE_MINDMAP.exists():
        return False
    text = orig = ARCHITECTURE_MINDMAP.read_text(encoding="utf-8")
    f = ARCHITECTURE_MINDMAP.name

    text = _patch(text, r"\*\*Last Updated:\*\* \S+", f"**Last Updated:** {today}", f)
    # Legacy table row — present in older regenerations, absent in newer ones; skip silently
    text = re.sub(r"\| \*\*Generated\*\* \| [^\|]+ \|", f"| **Generated** | {today} |", text)
    if py:
        text = _patch(text, r"~\d+\+? source files", f"~{py} source files", f)
    if models:
        # "131+ LLM models" in prose, and "| **Models Supported** | 100+" in table
        text = re.sub(r"\b\d+\+? LLM models\b", f"{models}+ LLM models", text)
        text = re.sub(r"(\| \*\*Models Supported\*\* \| )\d+\+?", rf"\g<1>{models}+", text)
    if presets:
        text = re.sub(r"\b\d+\+? declarative presets\b", f"{presets}+ declarative presets", text)
        text = re.sub(r"(\| \*\*Presets\*\* \| )\d+\+?", rf"\g<1>{presets}+", text)
    if methods:
        text = _patch(text, r"\| \*\*Reasoning Methods\*\* \| \d+", f"| **Reasoning Methods** | {methods}", f)

    if text == orig:
        return False
    ARCHITECTURE_MINDMAP.write_text(text, encoding="utf-8")
    _stage(ARCHITECTURE_MINDMAP)
    return True


def _update_codebase_mindmap(today: str, py: int, models: int, presets: int, methods: int) -> bool:
    if not CODEBASE_MINDMAP.exists():
        return False
    text = orig = CODEBASE_MINDMAP.read_text(encoding="utf-8")
    f = CODEBASE_MINDMAP.name

    # Both plain and bold "Last updated" forms
    text = re.sub(r"(\*\*Last updated:\*\*|Last updated:) \S+", rf"\1 {today}", text)
    # Header stats: both plain "Python source files: N" and bold "**Python source files:** N"
    if py:
        text = re.sub(r"(\*\*Python source files:\*\*|Python source files:) \d+", rf"\1 {py}", text)
    if models:
        text = re.sub(r"(\*\*Models:\*\*|Models:) \d+", rf"\1 {models}", text)
    if presets:
        text = re.sub(r"(\*\*Presets:\*\*|Presets:) \d+", rf"\1 {presets}", text)
    if methods:
        text = re.sub(r"(\*\*Methods:\*\*|Methods:) \d+", rf"\1 {methods}", text)

    if text == orig:
        return False
    CODEBASE_MINDMAP.write_text(text, encoding="utf-8")
    _stage(CODEBASE_MINDMAP)
    return True


def _update_codemaps(today: str, py: int) -> int:
    if not CODEMAPS_DIR.exists():
        return 0
    updated = 0
    for md in CODEMAPS_DIR.glob("*.md"):
        text = orig = md.read_text(encoding="utf-8")
        text = re.sub(
            r"<!-- Generated: \d{4}-\d{2}-\d{2} \| Files scanned: \d+",
            f"<!-- Generated: {today} | Files scanned: {py}",
            text,
        )
        if text != orig:
            md.write_text(text, encoding="utf-8")
            _stage(md)
            updated += 1
    return updated


# ── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    today = date.today().isoformat()
    py = _count_py_files()
    models = _count_models()
    presets = _count_presets()
    methods = _count_methods()

    changed: list[str] = []

    if _update_architecture_mindmap(today, py, models, presets, methods):
        changed.append("ARCHITECTURE_MINDMAP.md")

    if _update_codebase_mindmap(today, py, models, presets, methods):
        changed.append("docs/CODEBASE_MINDMAP.md")

    n = _update_codemaps(today, py)
    if n:
        changed.append(f"docs/CODEMAPS/ ({n} files)")

    if changed:
        print(
            f"[mindmap] Updated {', '.join(changed)} — "
            f"date={today}, py={py}, models={models}, presets={presets}, methods={methods}"
        )
    else:
        print("[mindmap] No metadata changes detected.")


if __name__ == "__main__":
    main()
