import os

# Mirror the env the CI test job sets (.github/workflows/test.yml) so a local
# `pytest tests/` behaves the same as CI. Without JWT_SECRET_KEY in particular,
# ~9 test modules fail at COLLECTION -- LocalAuthAdapter validates the key's
# length when it is constructed at module import time (e.g. test_ocr.py), so
# the error happens before any test runs and takes the whole file with it.
#
# setdefault, not assignment: a value already exported by CI or by a developer
# with real credentials always wins. These are placeholders, never credentials,
# and they are confined to the test process -- production still requires the
# real values via settings.
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production-use-only")
os.environ.setdefault("CSRF_ENFORCE_BACKEND", "false")
# Must look like a real key (sk-/sk-or- prefix): health_validator.validate_all(),
# triggered by any test that starts the FastAPI app lifespan, treats a
# malformed key as "missing" and permanently flips settings.COHERE_RERANK_ENABLED /
# DOCUMENT_SEMANTIC_RETRIEVAL_ENABLED to False via direct attribute assignment on the
# frozen settings singleton -- no restore, so it silently poisons every later
# test sharing that xdist worker.
os.environ.setdefault("OPENROUTER_API_KEY", "sk-or-test-dummy-openrouter-key-placeholder")
os.environ.setdefault("RATE_LIMITER_REDIS_FAILURE_MODE", "fail_open")

import asyncio

import pytest

from reasoner.application.event_bus.bus import reset_event_bus
from reasoner.core.ports.model_registry_port import set_model_registry_port
from reasoner.core.ports.shared_cache_port import set_shared_cache_port
from reasoner.core.rerank import reset_rerank_circuit
from reasoner.infrastructure.llm.registry import RegistryAdapter
from reasoner.infrastructure.rate_limiter import reset_rate_limiter_state
from reasoner.infrastructure.observability.langfuse_subscriber import reset_langfuse
from reasoner.token_cache import reset_token_cache

# The port is a process-global injected by each composition root (api/__init__.py,
# main.py, headless.py). Tests have no composition root, so anything reaching
# get_model_registry_port() raised "ModelRegistryPort not injected" unless some
# earlier test happened to import the app first — making failures depend on
# collection order and on how xdist sharded the run. Done at import time rather
# than in a fixture so it is in place before collection, and once per worker.
set_model_registry_port(RegistryAdapter())


@pytest.fixture(autouse=True)
async def auto_clean_state():
    """Fixture to reset all global state between tests."""
    # core.rerank latches a module-level failure counter open after 3 failures.
    # test_cohere_rerank.py drives enough failing calls to trip it, and the
    # circuit then short-circuits rerank_documents() for every later test on the
    # same xdist worker -- which looked like an unrelated broken fallback in
    # test_auto_rollback.py. Sync and loop-independent, so it runs outside the
    # loop branches below.
    reset_rerank_circuit()

    # The rate limiter keys its in-memory buckets by client IP, and every
    # TestClient request presents the same one, so the bucket drains as a
    # session progresses and later API tests get 429s instead of the response
    # they assert on. Same shape as the rerank circuit above: sync and
    # loop-independent, so it runs outside the loop branches below.
    reset_rate_limiter_state()

    # api/__init__.py's lifespan injects a real SharedCachePort on startup
    # and (as of this fix) clears it on shutdown -- but any test that starts
    # the app without a matching clean shutdown, or that ran before this
    # fix landed, can still leave a real adapter injected. A test whose
    # fake gate has no .router attribute then breaks only when this global
    # happens to be non-None, which depends on xdist worker assignment and
    # collection order, not on the test's own logic. Same shape as the
    # rerank circuit and rate limiter above.
    set_shared_cache_port(None)

    # Ensure event loop is running for async resets
    if asyncio.get_event_loop().is_running():
        reset_event_bus()
        reset_langfuse()
        await reset_token_cache()
    else:
        # If loop is not running, create a new one for the reset operations
        async def _run_resets():
            reset_event_bus()
            reset_langfuse()
            await reset_token_cache()
        asyncio.run(_run_resets())

    yield

    # Also reset after the test
    if asyncio.get_event_loop().is_running():
        reset_event_bus()
        reset_langfuse()
        await reset_token_cache()
    else:
        async def _run_resets_after():
            reset_event_bus()
            reset_langfuse()
            await reset_token_cache()
        asyncio.run(_run_resets_after())
