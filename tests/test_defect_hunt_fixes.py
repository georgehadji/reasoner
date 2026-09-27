"""Regression tests for defects found during autonomous defect hunt V7.

Each test reproduces the original defect (fails without the fix, passes with it).
"""
from __future__ import annotations

import asyncio
import os
import pytest

os.environ.setdefault("CSRF_SECRET", "test-secret-that-is-long-enough-32chars")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key-long-enough-32chars")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-long-enough-32chars")


# ── D1: DegradedLLMResponse.tokens_total and to_dict referenced nonexistent attrs ──

def test_degraded_response_tokens_total() -> None:
    """D1: tokens_total must return sum from metadata, not crash with AttributeError."""
    from reasoner.infrastructure.llm.ports import DegradedLLMResponse

    resp = DegradedLLMResponse(
        text="fallback",
        metadata={"input_tokens": 100, "output_tokens": 50, "model": "m", "finish_reason": "stop"},
        degraded=True,
        error="all failed",
    )
    assert resp.tokens_total == 150


def test_degraded_response_to_dict() -> None:
    """D1: to_dict must use actual dataclass fields, not nonexistent ones."""
    from reasoner.infrastructure.llm.ports import DegradedLLMResponse

    resp = DegradedLLMResponse(
        text="fallback",
        metadata={"input_tokens": 10, "output_tokens": 5, "model": "m", "finish_reason": "stop"},
    )
    d = resp.to_dict()
    assert d["content"] == "fallback"
    assert d["model_used"] == "m"
    assert d["tokens"]["total"] == 15
    assert d["finish_reason"] == "stop"


def test_degraded_response_empty_metadata() -> None:
    """D1 boundary: empty metadata yields zero tokens and 'unknown' model."""
    from reasoner.infrastructure.llm.ports import DegradedLLMResponse

    resp = DegradedLLMResponse()
    assert resp.tokens_total == 0
    d = resp.to_dict()
    assert d["model_used"] == "unknown"


# ── D2: Global provider cache key collision across different extra_body configs ──

def test_cache_key_distinguishes_extra_body() -> None:
    """D2: resolve() must not return a cached provider with different extra_body."""
    from reasoner.infrastructure.llm.router import _GLOBAL_RESOLVED_CACHE, ProviderRouter
    from reasoner.infrastructure.llm.base import BaseLLMProvider

    class Fake(BaseLLMProvider):
        def __init__(self, model: str, extra_body: dict | None = None) -> None:
            self.model = model
            self.extra_body = extra_body
            self.max_retries = 3

        async def complete(self, *a, **kw) -> str:
            return ""

        async def stream_complete(self, *a, **kw):
            yield ""

    _GLOBAL_RESOLVED_CACHE.clear()
    try:
        p1 = Fake("m", extra_body={"effort": "high"})
        p2 = Fake("m", extra_body={"effort": "low"})
        r1 = ProviderRouter(primary=p1, routing_table={"g": p1})
        r2 = ProviderRouter(primary=p2, routing_table={"g": p2})

        assert r1.resolve("g").extra_body == {"effort": "high"}
        assert r2.resolve("g").extra_body == {"effort": "low"}
    finally:
        _GLOBAL_RESOLVED_CACHE.clear()


# ── D5: Stream retry after partial yield produces duplicate content ──

@pytest.mark.asyncio
async def test_stream_no_retry_after_partial_yield() -> None:
    """D5: stream_complete_with_retry must not retry after chunks were already yielded."""
    from reasoner.infrastructure.llm.base import BaseLLMProvider

    class PartialFail(BaseLLMProvider):
        def __init__(self) -> None:
            self.model = "t"
            self.max_retries = 2
            self.calls = 0

        async def complete(self, *a, **kw) -> str:
            return ""

        async def stream_complete(self, *a, **kw):
            self.calls += 1
            yield "A"
            raise ConnectionError("mid-stream")

    p = PartialFail()
    chunks: list[str] = []
    with pytest.raises(ConnectionError):
        async for c in p.stream_complete_with_retry("s", "u"):
            chunks.append(c)

    assert p.calls == 1, "must not retry after partial yield"
    assert chunks == ["A"]


def test_degraded_response_is_falsy():
    """A failure object must not read as success to a naive caller.

    router.call returns ``str | DegradedLLMResponse``, and a dataclass instance
    is truthy by default, so ``if not response:`` used to pass straight over a
    total provider failure. The production path uses isinstance checks and was
    never fooled; the e2e suite's ``assert response`` was.
    """
    from reasoner.infrastructure.llm.ports import DegradedLLMResponse

    degraded = DegradedLLMResponse(text="", error="all providers down")
    assert not degraded
    assert bool(degraded) is False
    # isinstance-based detection must keep working unchanged
    assert isinstance(degraded, DegradedLLMResponse)
    assert degraded.degraded is True
    assert degraded.error == "all providers down"


# ── The two BaseLLMProvider / LLMError pairs must not be confusable ──

def test_one_error_tree_reaches_the_router():
    """Every LLMError spelling must resolve to something the router catches.

    Two unrelated LLMError classes used to live here: base.LLMError (a
    ReasonerError) and exceptions.LLMError (an InfrastructureError), neither a
    subclass of the other. The router caught the base one, so an
    exceptions.LLMError raised from a provider walked straight past the
    fallback chain -- the same defect as the raw SDK exceptions fixed in
    4af087e.

    P2 (docs/plans/root-cause-remediation-2026-09-07.md) collapsed them: the
    infrastructure module is now an alias shim, and base.LLMError descends from
    core.exceptions.ProviderError, which is what the router catches.
    """
    from reasoner.core.exceptions import ProviderError
    from reasoner.infrastructure.llm import LLMError as exported
    from reasoner.infrastructure.llm.base import LLMError as base_error
    from reasoner.infrastructure.llm.exceptions import LLMError as legacy

    assert exported is base_error
    assert legacy is base_error, "the deprecated module must alias, not redefine"
    assert issubclass(base_error, ProviderError), (
        "the router catches ProviderError; an LLMError outside that tree "
        "escapes the fallback chain entirely"
    )


def test_deprecated_exceptions_module_warns_on_import():
    """The compat shim must announce itself, so the aliases can be deleted."""
    import importlib
    import sys

    sys.modules.pop("reasoner.infrastructure.llm.exceptions", None)
    with pytest.warns(DeprecationWarning, match="reasoner.core.exceptions"):
        importlib.import_module("reasoner.infrastructure.llm.exceptions")


def test_every_provider_error_subclass_reaches_the_router():
    """Each leaf the adapters can raise must be caught by the router's except.

    ProviderCreditsExhaustedError is the one this is really about: it lived in
    the infrastructure tree, so a 402 escaped ProviderRouter._execute_call and
    was caught only by the `except Exception` in flows/runner.py (D5).
    """
    from reasoner.core.exceptions import (
        AuthenticationError,
        ModelNotFoundError,
        ProviderCreditsExhaustedError,
        ProviderError,
        ProviderTimeoutError,
        ProviderUnavailableError,
        RateLimitError,
    )

    for cls in (
        AuthenticationError, RateLimitError, ModelNotFoundError,
        ProviderTimeoutError, ProviderUnavailableError,
        ProviderCreditsExhaustedError,
    ):
        assert issubclass(cls, ProviderError), cls.__name__


def test_package_exports_the_provider_base_the_router_can_call():
    """The exported BaseLLMProvider must be the one ProviderRouter can drive.

    ports.BaseLLMProvider is a different interface (complete(messages, config)
    -> LLMResponse) with no complete_with_retry(), which is what the router
    calls. Exporting it produced routers that raised AttributeError on their
    first call.
    """
    from reasoner.infrastructure.llm import BaseLLMProvider as exported
    from reasoner.infrastructure.llm.base import BaseLLMProvider as router_expects

    assert exported is router_expects
    assert hasattr(exported, "complete_with_retry")
    # P2 deleted the other one outright, so the trap can no longer be sprung.
    import reasoner.infrastructure.llm.ports as ports
    assert not hasattr(ports, "BaseLLMProvider")


def test_noop_provider_serves_a_router_instead_of_raising():
    """The no-API-key path must return its canned message, not AttributeError.

    api/__init__.py falls back to NoopProvider when no provider is available
    and feeds it to ProviderRouter. NoopProvider subclassed ports, so every
    call raised:

        AttributeError: 'NoopProvider' object has no attribute 'complete_with_retry'
    """
    from reasoner.infrastructure.llm.providers.noop import NoopProvider
    from reasoner.infrastructure.llm.router import ProviderRouter

    router = ProviderRouter(primary=NoopProvider(model="dummy"))
    response, metadata = asyncio.run(
        router.call(
            role="classification",
            system_prompt="s",
            user_prompt="u",
            max_tokens=32,
            temperature=0.1,
        )
    )
    assert response == "Dummy provider - configure API keys"
    assert metadata["model"] == "dummy"


def test_ports_defines_neither_errors_nor_a_second_provider_base():
    """ports.py holds data types and one Protocol. Nothing else.

    It used to carry a third LLMError tree (dead: nothing imported it, not even
    this module) and a second BaseLLMProvider with an incompatible interface
    and no complete_with_retry(). Both are deleted in P2; what a caller needs
    from here is Message/LLMConfig/LLMResponse/DegradedLLMResponse.
    """
    from reasoner.infrastructure.llm import ports

    for gone in ("BaseLLMProvider", "LLMError", "AuthenticationError",
                 "ProviderUnavailableError", "is_retryable"):
        assert not hasattr(ports, gone), f"ports.{gone} is back"
    for kept in ("Message", "LLMConfig", "LLMResponse", "DegradedLLMResponse",
                 "LLMProvider"):
        assert hasattr(ports, kept), f"ports.{kept} went missing"
