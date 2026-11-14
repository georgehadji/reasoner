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


def test_choke_point_counts_detection_and_reroute(monkeypatch):
    from reasoner.core.ports import metrics_port
    from reasoner.core.settings import settings
    from reasoner.hypergate.hyperagent import HyperGateAgent

    seen = []
    monkeypatch.setattr(metrics_port, "_STAKES_COUNTER", lambda k, a, b: seen.append((k, a, b)))
    monkeypatch.setattr(settings, "STAKES_POLICY_MODE", "active")
    HyperGateAgent._apply_stakes("What is the max dosage of ibuprofen?", _d("direct"))
    assert seen == [("detected", "health", "regex"), ("rerouted", "direct", "")]


# ── model detector (plan §1.3) ──────────────────────────────────────────


def _ctx(domain="legal", confidence=0.9, error=None):
    from reasoner.hypergate.models import HyperContext, SubAgentOutput

    def out(result, conf=0.9, err=None):
        return SubAgentOutput("x", result, conf, "", 0, 0, "m", 0.0, err)

    return HyperContext(
        problem="p", lang_output=out({}), complexity_output=out({}),
        direct_output=out({}), web_output=out({}), method_output=out({}),
        stakes_output=out({"domain": domain}, confidence, error),
    )


@pytest.mark.parametrize("domain,conf,err,exp", [
    ("legal", 0.9, None, StakesDomain.LEGAL),
    ("health", 0.5, None, StakesDomain.NONE),      # below threshold
    ("legal", 0.9, "boom", StakesDomain.NONE),     # detector failed
    ("astrology", 0.9, None, StakesDomain.NONE),   # unknown domain
])
def test_model_stakes_reads_the_detector(domain, conf, err, exp):
    from reasoner.hypergate.hyperagent import HyperGateAgent

    assert HyperGateAgent._model_stakes(_ctx(domain, conf, err)) is exp


def test_detector_parse_failure_is_none():
    from reasoner.hypergate.sub_agents.stakes_detector import StakesDetectorSubAgent

    r = StakesDetectorSubAgent()._parse_result("not json")
    assert r["domain"] == "none" and r["confidence"] == 0.0


def test_model_domain_reroutes_when_regex_misses(monkeypatch):
    from reasoner.core.settings import settings
    from reasoner.hypergate.hyperagent import HyperGateAgent

    monkeypatch.setattr(settings, "STAKES_POLICY_MODE", "active")
    problem = "my landlord keeps my deposit, what now"  # no regex hit expected
    out = HyperGateAgent._apply_stakes(problem, _d("direct"), StakesDomain.LEGAL)
    assert out.action == "pipeline" and out.stakes["source"] == "llm"


def test_to_dict_still_strips_method_names_with_stakes_output():
    d = _ctx().to_dict()
    assert "stakes" not in str(d.keys())
