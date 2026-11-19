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


def _order(tier: str) -> list[str]:
    block = re.search(rf"{tier}: \[(.*?)\]", _METHODS_TS.read_text(encoding="utf-8"), re.S)
    return re.findall(r"'([a-z-]+)'", block.group(1))


@pytest.mark.parametrize("tier", ["budget", "premium"])
def test_menu_is_ordered_cheapest_first(tier: str) -> None:
    from reasoner.application.services.spend_limit_service import estimate_run_cost

    order = _order(tier)
    assert sorted(order) == sorted(_SLUGS), "the order must list every menu method once"
    costs = [estimate_run_cost(f"{slug}-{tier}") for slug in order]
    out_of_order = [(a, b) for a, b, ca, cb in zip(order, order[1:], costs, costs[1:]) if ca > cb]
    assert not out_of_order, f"{tier}: re-sort METHOD_ORDER_BY_COST; costlier first: {out_of_order}"


@pytest.mark.parametrize("slug", _SLUGS)
def test_every_menu_method_has_all_four_presets(slug: str) -> None:
    wanted = [f"{slug}-{w}{t}" for w in ("", "western-") for t in ("budget", "premium")]
    assert [p for p in wanted if p not in PRESETS] == []
