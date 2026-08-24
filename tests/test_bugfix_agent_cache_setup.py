from reasoner.hypergate.base_sub_agent import BaseSubAgent
from reasoner.subagents.base import PhaseSubAgent


class DummyPhaseSubAgent(PhaseSubAgent):
    """Dummy PhaseSubAgent for testing initialization."""
    def _build_prompt(self, state):
        return "", ""
    def _parse_result(self, raw):
        return {}

class DummyHyperBaseSubAgent(BaseSubAgent):
    """Dummy BaseSubAgent for testing initialization."""
    def _system_prompt(self):
        return ""
    def _parse_result(self, raw):
        return {}
    async def execute(self, state, router):
        pass

def test_phase_subagent_cache_instantiation():
    """
    Tests that the _cache attribute is correctly instantiated as a concrete dictionary
    on the instance, verifying that the removal of type hints inside __new__ prevents
    the AttributeError setup bug in test fixtures.
    """
    agent1 = DummyPhaseSubAgent()
    assert hasattr(agent1, "_cache")
    assert isinstance(agent1._cache, dict)

    agent2 = DummyHyperBaseSubAgent()
    assert hasattr(agent2, "_cache")
    assert isinstance(agent2._cache, dict)
