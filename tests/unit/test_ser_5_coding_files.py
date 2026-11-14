"""The coding method's last phase must send the code, not only the file paths.

Final Assembly is the coding flow's final phase, so its frame is the answer.
_ser_5 sent ``final_files`` as ``{path, changed}`` only, and the browser had
nothing to render: a coding run ended on an empty answer card.
"""

from __future__ import annotations

from reasoner.application.services.serializers import _ser_5
from reasoner.domain.pipeline_state import PipelineState


def test_final_files_carry_their_content():
    state = PipelineState(problem="merge intervals")
    state.coding_state = {
        "language": "python",
        "final_files": [
            {"path": "intervals.py", "content": "def merge(xs):\n    return xs\n", "changed": True},
        ],
        "readme": "Merges overlapping intervals.",
    }

    files = _ser_5(state)["coding_state"]["final_files"]

    assert files == [
        {
            "path": "intervals.py",
            "content": "def merge(xs):\n    return xs\n",
            "language": "python",
            "changed": True,
        }
    ]
