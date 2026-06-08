"""
Update dynamic metadata in ARCHITECTURE_MINDMAP.md after each commit.

Updates: Last Updated date, Python source file count, model count,
preset count, reasoning method count — all derived from live code.
Leaves all architectural prose untouched.
"""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MINDMAP = ROOT / "ARCHITECTURE_MINDMAP.md"


def _count_py_files() -> int:
    src = ROOT / "src" / "reasoner"
    return len(list(src.rglob("*.py"))) if src.exists() else 0


def _count_models() -> int:
    try:
        import importlib, sys as _sys
        _sys.path.insert(0, str(ROOT / "src"))
        mod = importlib.import_module("reasoner.infrastructure.llm.registry")
        whitelist = getattr(mod, "_MODEL_WHITELIST", None)
        return len(whitelist) if whitelist else 0
    except Exception:
        return 0


def _count_presets() -> int:
    try:
        import importlib, sys as _sys
        _sys.path.insert(0, str(ROOT / "src"))
        mod = importlib.import_module("reasoner.presets")
        presets = getattr(mod, "PRESETS", None)
        return len(presets) if presets else 0
    except Exception:
        return 0


def _count_methods() -> int:
    phases_dir = ROOT / "src" / "reasoner" / "phases"
    if not phases_dir.exists():
        return 0
    # Each method has a dedicated prompt module (exclude _shared and _universal)
    return len([
        f for f in phases_dir.glob("*.py")
        if not f.stem.startswith("_") and f.stem not in ("__init__",)
    ])


def _patch(text: str, pattern: str, replacement: str) -> str:
    new, n = re.subn(pattern, replacement, text, count=1)
    if n == 0:
        print(f"  [mindmap] WARNING: pattern not found — {pattern!r}", file=sys.stderr)
    return new


def main() -> None:
    if not MINDMAP.exists():
        print("[mindmap] ARCHITECTURE_MINDMAP.md not found — skipping", file=sys.stderr)
        sys.exit(0)

    today = date.today().isoformat()
    py_files = _count_py_files()
    models = _count_models()
    presets = _count_presets()
    methods = _count_methods()

    text = MINDMAP.read_text(encoding="utf-8")
    original = text

    text = _patch(text, r"\*\*Last Updated:\*\* \S+", f"**Last Updated:** {today}")
    text = _patch(text, r"\| \*\*Generated\*\* \| [^\|]+ \|", f"| **Generated** | {today} |")

    if py_files:
        text = _patch(
            text,
            r"~\d+ source files",
            f"~{py_files} source files",
        )
    if models:
        text = _patch(
            text,
            r"\b\d+\+ LLM models\b",
            f"{models}+ LLM models",
        )
    if presets:
        text = _patch(
            text,
            r"\b\d+ declarative presets\b",
            f"{presets} declarative presets",
        )
    if methods:
        text = _patch(
            text,
            r"\| \*\*Reasoning Methods\*\* \| \d+",
            f"| **Reasoning Methods** | {methods}",
        )

    if text == original:
        print("[mindmap] No metadata changes detected.")
        sys.exit(0)

    MINDMAP.write_text(text, encoding="utf-8")
    print(
        f"[mindmap] Updated metadata: date={today}, py={py_files}, "
        f"models={models}, presets={presets}, methods={methods}"
    )

    # Stage the updated file so it's included in the next commit
    # (runs inside post-commit, so we amend-stage without re-triggering the hook)
    subprocess.run(
        ["git", "add", str(MINDMAP.relative_to(ROOT))],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )


if __name__ == "__main__":
    main()
