"""The run card's phase plans must match the backend flows.

``ui-next/src/lib/method-phases.generated.ts`` is written by
``scripts/gen_method_phases.py`` from each flow's ``get_phases``. A flow that
adds, drops or renames a step without regenerating it makes the card count
the wrong steps, which is how the hand-written plans drifted before.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_generated_method_phases_are_current():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "gen_method_phases.py"), "--check"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr
