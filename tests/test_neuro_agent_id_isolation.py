"""agent_id reaches the neuro data dir straight from request bodies
(/api/neuro/{recall,learn,audit}) and from PipelineState.conversation_id.
It is joined onto a filesystem path, so it must never escape agents/.
"""

import pytest

from reasoner.neuro.config import NeuroConfig, get_agent_data_dir


@pytest.fixture
def cfg(tmp_path):
    c = NeuroConfig()
    c.data_dir = str(tmp_path)
    return c


@pytest.mark.parametrize("agent_id", [
    "/etc/evil",              # absolute path — wins the join outright
    r"C:\Windows\evil",     # absolute path, Windows form
    "../../../../tmp/pwn",    # relative traversal
    "..",
    ".",
    "a/../../b",
    "",
    "   ",
    "\x00null",
])
def test_hostile_agent_id_stays_under_agents_dir(cfg, agent_id, tmp_path):
    resolved = get_agent_data_dir(cfg, agent_id).resolve()
    agents_root = (tmp_path / "agents").resolve()
    assert resolved.is_relative_to(agents_root), (
        f"agent_id {agent_id!r} escaped to {resolved}"
    )
    # and it must be a single segment, not a nested path
    assert len(resolved.relative_to(agents_root).parts) == 1


def test_benign_agent_id_is_preserved(cfg, tmp_path):
    aid = "018f3c9a-7b2e-4d1f-9c8a-1a2b3c4d5e6f"
    assert get_agent_data_dir(cfg, aid) == tmp_path / "agents" / aid


def test_distinct_agents_get_distinct_dirs(cfg):
    assert get_agent_data_dir(cfg, "alice") != get_agent_data_dir(cfg, "bob")


def test_none_agent_id_falls_back_to_default(cfg, tmp_path):
    assert get_agent_data_dir(cfg, None) == tmp_path / "agents" / "default"


def test_configured_agent_with_explicit_data_dir_is_trusted(cfg, tmp_path):
    """Operator config (neuro.yaml) is trusted and may point anywhere."""
    from reasoner.neuro.config import AgentConfig

    custom = tmp_path / "elsewhere"
    cfg.agents["ops"] = AgentConfig(data_dir=str(custom))
    assert get_agent_data_dir(cfg, "ops") == custom
