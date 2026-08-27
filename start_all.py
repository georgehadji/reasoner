"""Orchestrator shim. Keeps `python start_all.py` working."""
import sys
from pathlib import Path

SRC = str(Path(__file__).parent / "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

try:
    from reasoner.start_all import main
except ImportError as exc:
    # A missing dependency is the most common first-run failure, and a bare
    # traceback in a launcher window that closes says nothing actionable.
    print(f"[ERROR] Could not import the Reasoner package: {exc}")
    print()
    print("        1. Install dependencies:  pip install -r requirements.txt")
    print(f"        2. Check the interpreter: {sys.executable}")
    print("           (Python 3.12+ is required)")
    print("        3. Confirm src/reasoner/ exists in this checkout.")
    sys.exit(1)
except RuntimeError as exc:
    # reasoner.core.settings validates configuration at import time and
    # raises for a missing secret. That is the second thing a fresh checkout
    # hits, and it is a config problem, not a broken install — say so
    # instead of printing a stack that points into settings.py.
    print(f"[ERROR] Configuration rejected at startup: {exc}")
    print()
    print("        Copy .env.example to .env and fill in the value it names.")
    sys.exit(1)

if __name__ == "__main__":
    sys.exit(main())
