"""CLI entry-point shim. Keeps `python main.py` working."""
import asyncio
import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from reasoner.main import main, parse_args

if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args))
