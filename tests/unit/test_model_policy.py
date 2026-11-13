"""core/model_policy: the per-run bloc restriction behind Western-only runs."""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from reasoner.core import model_policy  # noqa: E402
from reasoner.core.model_policy import (  # noqa: E402
    WESTERN_BLOCS,
    ModelNotAllowedError,
    restrict_blocs,
    run_blocs,
)
from reasoner.domain.preset_core import FOLLOWUP_AGENT_MODELS_WESTERN, is_western_preset  # noqa: E402
from reasoner.domain.preset_registry import _REGISTRY as PRESETS  # noqa: E402
from reasoner.infrastructure.llm.registry import bloc_of, build_provider  # noqa: E402


@pytest.mark.unit
def test_build_provider_refuses_cn_only_inside_a_western_run(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    build_provider("deepseek-v4-flash")  # unrestricted: builds
    with restrict_blocs(WESTERN_BLOCS):
        with pytest.raises(ModelNotAllowedError):
            build_provider("deepseek-v4-flash")
        build_provider("mistral-small")
    assert model_policy.allowed_blocs() is None


@pytest.mark.unit
def test_restriction_reaches_child_tasks():
    """Phase-2 generators run as gathered tasks; they must inherit the policy."""
    async def child() -> frozenset[str] | None:
        return model_policy.allowed_blocs()

    async def run() -> list:
        with restrict_blocs(WESTERN_BLOCS):
            return await asyncio.gather(child(), asyncio.create_task(child()))

    assert asyncio.run(run()) == [WESTERN_BLOCS, WESTERN_BLOCS]


@pytest.mark.unit
def test_direct_fallback_chain_skips_cn_providers():
    from reasoner.infrastructure.llm.providers.direct import build_fallback_provider

    with restrict_blocs(WESTERN_BLOCS):
        for name in ("deepseek", "qwen"):
            with pytest.raises(ModelNotAllowedError):
                build_fallback_provider(name)


@pytest.mark.unit
def test_image_models_are_checked_too():
    from reasoner.infrastructure.llm.image_generation import _resolve_model_config

    with restrict_blocs(WESTERN_BLOCS):
        with pytest.raises(ModelNotAllowedError):
            _resolve_model_config("seedream-4.5")
        assert _resolve_model_config("flux.2-pro")


@pytest.mark.unit
def test_run_blocs_follows_the_preset_id():
    assert run_blocs("debate-western-budget") == WESTERN_BLOCS
    assert run_blocs("auto-western-premium") == WESTERN_BLOCS
    assert run_blocs("debate-budget") is None
    assert run_blocs(None) is None
    for pid in PRESETS:
        assert (run_blocs(pid) is not None) == is_western_preset(pid), pid


@pytest.mark.unit
def test_memory_store_is_separate_and_anonymous_stays_anonymous():
    assert model_policy.memory_agent_id("conv1") == "conv1"
    with restrict_blocs(WESTERN_BLOCS):
        assert model_policy.memory_agent_id("conv1") == "conv1-western"
        assert model_policy.memory_agent_id(None) is None
    assert model_policy.is_western_memory("u-x-conv1-western")


@pytest.mark.unit
def test_western_embedding_has_no_cn_fallback():
    from reasoner.neuro.config import ResilientProviderConfig, western_embedding_config

    cfg = western_embedding_config(ResilientProviderConfig())
    assert cfg.primary.model.startswith("openai/")
    assert cfg.fallbacks == []


@pytest.mark.unit
def test_followup_defaults_are_western():
    assert all(bloc_of(m) in WESTERN_BLOCS for m in FOLLOWUP_AGENT_MODELS_WESTERN.values())


@pytest.mark.unit
def test_request_maps_to_twin_and_rejects_cn_models():
    from pydantic import ValidationError

    from reasoner.api.schemas import RunRequest

    assert RunRequest(problem="q", preset="debate-budget", western_only=True).preset == (
        "debate-western-budget"
    )
    assert RunRequest(problem="q", preset="auto-budget", western_only=True).preset == (
        "auto-western-budget"
    )
    with pytest.raises(ValidationError, match="non-US/EU"):
        RunRequest(
            problem="q", preset="debate-western-budget",
            routing={"synthesis": "deepseek-v4-flash"},
        )
