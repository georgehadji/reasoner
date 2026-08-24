"""Orchestrator shim. Keeps `python start_all.py` working."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
from reasoner.start_all import main

if __name__ == "__main__":
    sys.exit(main())
