"""The composer's method menu sends `<slug>[-western]-<tier>`; every such preset must exist.

A slug in ui-next/src/lib/methods.ts with a missing preset would fail the run
only after the user picked it, so check the whole menu here.
"""

import re
from pathlib import Path

import pytest

from reasoner.presets import PRESETS

_METHODS_TS = Path(__file__).resolve().parents[2] / "ui-next" / "src" / "lib" / "methods.ts"
_SLUGS = re.findall(r"slug: '([a-z-]+)'", _METHODS_TS.read_text(encoding="utf-8"))


def test_menu_is_parsed() -> None:
    assert len(_SLUGS) >= 20


@pytest.mark.parametrize("slug", _SLUGS)
def test_every_menu_method_has_all_four_presets(slug: str) -> None:
    wanted = [f"{slug}-{w}{t}" for w in ("", "western-") for t in ("budget", "premium")]
    assert [p for p in wanted if p not in PRESETS] == []
