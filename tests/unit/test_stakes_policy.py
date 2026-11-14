import pytest

from reasoner.domain.stakes import StakesDomain, StakesProfile
from reasoner.hypergate.gate_agent import GateDecision
from reasoner.hypergate.stakes_policy import apply_stakes_policy

HIGH = StakesProfile(domain=StakesDomain.HEALTH, confidence=1.0)
LOW = StakesProfile()


def _d(action, method=None):
    return GateDecision(action=action, method=method, confidence=0.9, complexity="simple")


@pytest.mark.parametrize("action,method,exp_action,exp_method", [
    ("direct", None, "pipeline", "research"),
    ("web_search", None, "pipeline", "research"),
    ("pipeline", "debate", "pipeline", "research"),
    ("pipeline", "research", "pipeline", "research"),
    ("pipeline", "cove", "pipeline", "cove"),
])
def test_high_stakes_table(action, method, exp_action, exp_method):
    out = apply_stakes_policy(_d(action, method), HIGH)
    assert (out.action, out.method) == (exp_action, exp_method)
    assert out.stakes["domain"] == "health"


@pytest.mark.parametrize("action", ["direct", "web_search", "pipeline"])
def test_low_stakes_unchanged(action):
    d = _d(action)
    assert apply_stakes_policy(d, LOW) is d


def test_input_not_mutated():
    d = _d("direct")
    apply_stakes_policy(d, HIGH)
    assert d.action == "direct" and d.stakes is None


def test_domain_module_is_stdlib_only():
    import ast
    import pathlib

    import reasoner.domain.stakes as m

    tree = ast.parse(pathlib.Path(m.__file__).read_text(encoding="utf-8"))
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert mods <= {"__future__", "dataclasses", "datetime", "enum"}


@pytest.mark.parametrize(
    "mode,action", [("off", "direct"), ("shadow", "direct"), ("active", "pipeline")]
)
def test_agent_choke_point_modes(monkeypatch, mode, action):
    from reasoner.core.settings import settings
    from reasoner.hypergate.hyperagent import HyperGateAgent

    monkeypatch.setattr(settings, "STAKES_POLICY_MODE", mode)
    out = HyperGateAgent._apply_stakes("What is the max dosage of ibuprofen?", _d("direct"))
    assert out.action == action
    assert (out.stakes is not None) == (mode != "off")


def test_named_method_is_left_alone(monkeypatch):
    from reasoner.core.settings import settings
    from reasoner.hypergate.hyperagent import HyperGateAgent

    monkeypatch.setattr(settings, "STAKES_POLICY_MODE", "active")
    d = _d("pipeline", "debate")
    problem = "use the debate method: is it legal to sue my landlord"
    assert HyperGateAgent._apply_stakes(problem, d) is d
