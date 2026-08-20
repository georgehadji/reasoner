"""Pricing must resolve registry aliases in a process with no DI wiring.

Regression guard for the misprice that made the per-run spend gate blind.
``application/services/pricing_service.get_pricing`` resolved aliases through
``get_model_registry_port()``, which raises when nothing injected it, inside a
bare ``except Exception: pass``. Any process without a composition root -- the
CLI, MCP stdio, every test, and any API worker whose injection import failed --
therefore priced EVERY model at the ``_default`` $1/$5 per M.

The consequence was not a rounding error. ``estimate_run_cost`` backs
``check_run_allowed``, so the spend gate returned the same figure for a budget
preset and a premium one: measured $0.27288 for ``debate-budget`` against a
correctly-priced $0.062173, and a delta of exactly $0.0000 between two entirely
different routings.

These tests deliberately do NOT inject the port. That is the whole point: the
uninjected process is the one that used to be wrong.
"""
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from reasoner.domain.pricing import PRICING_DB  # noqa: E402
from reasoner.infrastructure.llm.pricing_resolver import get_pricing  # noqa: E402


@pytest.fixture
def no_registry_port(monkeypatch):
    """Force the "nothing injected" state regardless of test ordering.

    conftest.py injects the port for the wider suite, and other tests may have
    already done so in-process. Clearing the module global reproduces a fresh
    CLI/MCP process, which is the condition the bug needed.
    """
    import reasoner.core.ports.model_registry_port as port_mod

    monkeypatch.setattr(port_mod, "_REGISTRY_PORT", None, raising=False)
    with pytest.raises(RuntimeError):
        port_mod.get_model_registry_port()
    return port_mod


@pytest.mark.unit
def test_alias_resolves_without_the_registry_port(no_registry_port):
    """The exact assertion the bug report asked for."""
    pricing = get_pricing("deepseek-v4-flash")

    assert pricing is not PRICING_DB["_default"], (
        "deepseek-v4-flash priced at the _default entry with no port injected — "
        "the alias did not resolve. This is the original bug: pricing must not "
        "depend on request-time DI."
    )
    assert pricing == PRICING_DB["deepseek/deepseek-v4-flash"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "alias, served",
    [
        ("deepseek-v4-flash", "deepseek/deepseek-v4-flash"),
        ("gpt-5.6-luna", "openai/gpt-5.6-luna"),
        ("claude-sonnet", "anthropic/claude-sonnet-5"),
        ("grok-4.3", "x-ai/grok-4.3"),
        ("sonar", "perplexity/sonar"),
    ],
)
def test_aliases_price_as_their_served_model(no_registry_port, alias, served):
    assert get_pricing(alias) == PRICING_DB[served]


@pytest.mark.unit
def test_served_model_ids_still_resolve_directly(no_registry_port):
    """Callers may pass either form; the served path must not regress."""
    assert get_pricing("deepseek/deepseek-v4-flash") == PRICING_DB["deepseek/deepseek-v4-flash"]


@pytest.mark.unit
def test_distinct_routings_produce_distinct_estimates(no_registry_port):
    """The symptom that made the gate useless: every preset costing the same.

    A budget preset and a premium one must not estimate identically. Under the
    bug the delta was exactly 0.0 because every model hit the same default.
    """
    from reasoner.application.services import spend_limit_service as svc

    budget = svc.estimate_run_cost("debate-budget")
    premium = svc.estimate_run_cost("debate-premium")

    assert budget > 0 and premium > 0
    assert premium != budget, (
        "debate-budget and debate-premium estimate identically — pricing has "
        "collapsed to a flat rate again and the spend gate cannot tell tiers apart"
    )
    assert premium > budget


@pytest.mark.unit
def test_unpriceable_model_is_logged_not_swallowed(no_registry_port, caplog):
    """An unknown model may still fall back, but it must say so.

    The original defect was not the fallback itself -- it was that an
    uninjected port and a genuinely unknown model produced the identical
    silent result, so nothing downstream could tell a real price from a guess.
    """
    with caplog.at_level(logging.WARNING):
        pricing = get_pricing("definitely-not-a-real-model-xyz")

    assert pricing is PRICING_DB["_default"]
    rendered = [r.getMessage() for r in caplog.records]
    assert any("definitely-not-a-real-model-xyz" in m for m in rendered), (
        f"no warning logged for an unpriceable model; records={rendered}"
    )


@pytest.mark.unit
def test_known_alias_does_not_warn(no_registry_port, caplog):
    """Guard against the warning firing on the happy path and becoming noise."""
    with caplog.at_level(logging.WARNING):
        get_pricing("deepseek-v4-flash")

    noisy = [r.getMessage() for r in caplog.records if "No pricing for model" in r.getMessage()]
    assert not noisy, f"resolvable alias logged a warning: {noisy}"


@pytest.mark.unit
def test_application_layer_holds_no_pricing_shim():
    """The old application-layer module must stay deleted.

    It is re-addable by muscle memory, and re-adding it silently restores the
    DI dependency this fix removed.
    """
    src = Path(__file__).resolve().parent.parent.parent / "src"
    stale = src / "reasoner" / "application" / "services" / "pricing_service.py"
    assert not stale.exists(), (
        f"{stale} is back; alias-aware pricing belongs in "
        f"infrastructure/llm/pricing_resolver.py, which needs no injected port"
    )
