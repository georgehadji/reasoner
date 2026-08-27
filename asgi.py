"""ASGI entry-point. Run with: uvicorn asgi:app --host 0.0.0.0 --port 8003"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
from reasoner.api import app  # noqa: E402

__all__ = ["app"]
