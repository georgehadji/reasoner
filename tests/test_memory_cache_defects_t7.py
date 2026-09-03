"""T7 defect-hunt regression guards: neuro compression, L1 cache, HyperGate keys.

Three verified defects, each with its proof-of-defect, boundary cases and a
no-regression guard that the documented behaviour still happens.
"""

import asyncio

import pytest

from reasoner.hypergate.models import SubAgentInput
from reasoner.hypergate.sub_agents.tie_breaker import TieBreakerSubAgent
from reasoner.neuro.cache import L1Cache
from reasoner.neuro.compression import CompressionLevel, Language, smart_compress
from reasoner.neuro.config import CacheConfig

# -- D2: a mid-line "/*" silently discarded the rest of the text -------------


def test_midline_block_marker_does_not_discard_the_rest_of_the_text():
    """Proof-of-defect. `block_start in trimmed` opened block-comment mode on
    any line merely *containing* "/*" -- a glob, a URL, an SQL hint. Nothing
    later closed it, so compress() returned "" and every caller
    (/api/neuro/recall, pipeline E3, prompt code-fence compression) silently
    received an empty string in place of the content.
    """
    text = "Line one about src/*.ts globs\nLine two MUST SURVIVE\nLine three MUST SURVIVE"
    out = smart_compress(text, ext="", level="minimal")
    assert "MUST SURVIVE" in out
    assert out.count("MUST SURVIVE") == 2


@pytest.mark.parametrize(
    "text",
    [
        "See https://example.com/* for details\nSECOND LINE",
        "SELECT /*+ index(t) */ 1 FROM t\nSECOND LINE",
        "a/*b\nSECOND LINE",
    ],
)
def test_boundary_midline_markers_in_every_shape(text):
    assert "SECOND LINE" in smart_compress(text, ext="", level="minimal")


def test_boundary_empty_and_marker_only_input():
    assert smart_compress("", ext="", level="minimal") == ""
    assert smart_compress("/*", ext="", level="minimal") == ""
    # an unterminated comment that really does start the line still eats the
    # tail -- that is a genuine unterminated block comment, not a false trigger
    assert smart_compress("/* open\ncode", ext="", level="minimal") == ""


def test_no_regression_real_block_comments_are_still_removed():
    src = "/* header comment */\nint x = 1;\n/* second\n   comment */\nint y = 2;"
    out = smart_compress(src, ext="ts", level="minimal")
    assert "header comment" not in out
    assert "second" not in out
    assert "int x = 1;" in out
    assert "int y = 2;" in out


def test_no_regression_python_line_comments_still_removed():
    out = smart_compress("# a comment\nx = 1\n", ext="py", level="minimal")
    assert "# a comment" not in out
    assert "x = 1" in out


def test_no_regression_aggressive_still_keeps_only_signatures():
    src = "def f(a):\n    return a + 1\n"
    out = smart_compress(src, ext="py", level="aggressive")
    assert "def f(a):" in out
    assert "return a + 1" not in out


def test_no_regression_level_none_is_verbatim():
    src = "anything /* at all\nhere"
    assert smart_compress(src, ext="", level="none") == src
    assert CompressionLevel("aggressive") is CompressionLevel.AGGRESSIVE
    assert Language.from_extension(".PY") is Language.PYTHON


# -- D5: duplicate content double-appended, then evicted out from under itself --


def _cfg(max_bundles: int) -> CacheConfig:
    cfg = CacheConfig()
    cfg.l1_max_bundles = max_bundles
    return cfg


def test_re_adding_identical_content_does_not_lose_it_on_reload(tmp_path):
    """Proof-of-defect. bundle_id is a digest of the content and maps to one
    file, so appending a second in-memory entry for the same content left two
    list entries behind one file. Evicting either unlinked the file while the
    other stayed "present" in memory -- the entry then vanished at the next
    _load() (worker restart, tenant eviction).
    """
    cache = L1Cache(tmp_path, _cfg(3))

    async def go():
        await cache.add("same", "s", [1.0, 0.0])
        await cache.add("same", "s", [1.0, 0.0])
        await cache.add("b", "s", [1.0, 0.0])
        await cache.add("c", "s", [1.0, 0.0])

    asyncio.run(go())

    assert [b["content"] for b in cache.bundles] == ["same", "b", "c"]
    reloaded = L1Cache(tmp_path, _cfg(3))
    assert sorted(b["content"] for b in reloaded.bundles) == ["b", "c", "same"]


def test_boundary_search_does_not_return_one_memory_twice(tmp_path):
    cache = L1Cache(tmp_path, _cfg(50))
    asyncio.run(cache.add("dup", "s", [1.0, 0.0]))
    asyncio.run(cache.add("dup", "s", [1.0, 0.0]))
    hits = cache.search([1.0, 0.0], top_k=5)
    assert [h.content for h in hits] == ["dup"]


def test_boundary_readd_refreshes_rather_than_grows(tmp_path):
    cache = L1Cache(tmp_path, _cfg(50))
    asyncio.run(cache.add("x", "s", [1.0, 0.0]))
    first = cache.bundles[0]["created_at"]
    asyncio.run(cache.add("x", "other-source", [0.0, 1.0]))
    assert cache.size == 1
    assert cache.bundles[0]["source"] == "other-source"
    assert cache.bundles[0]["created_at"] >= first


def test_no_regression_distinct_content_still_evicts_oldest_first(tmp_path):
    cache = L1Cache(tmp_path, _cfg(2))

    async def go():
        for c in ("a", "b", "c"):
            await cache.add(c, "s", [1.0, 0.0])

    asyncio.run(go())
    assert [b["content"] for b in cache.bundles] == ["b", "c"]
    assert sorted(b["content"] for b in L1Cache(tmp_path, _cfg(2)).bundles) == ["b", "c"]


# -- D1: HyperGate sub-agent cache key ignored SubAgentInput.context ---------


class _ScriptedRouter:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    async def call(self, **kwargs):
        self.calls.append(kwargs["user_prompt"])
        return self.replies.pop(0), {"model": "fake", "input_tokens": 1, "output_tokens": 1}


def test_different_phase1_context_is_not_served_from_cache():
    """Proof-of-defect. The key was sha256(AGENT_NAME:problem); context is part
    of the user prompt (_llm_call), so TieBreaker -- whose entire job is to
    arbitrate the Phase-1 signals in context -- returned a verdict computed
    from a different set of signals for the same problem text.
    """
    agent = TieBreakerSubAgent()
    router = _ScriptedRouter(
        [
            '{"action":"direct","method":null,"confidence":0.9,"rationale":"A"}',
            '{"action":"pipeline","method":"debate","confidence":0.9,"rationale":"B"}',
        ]
    )

    async def go():
        a = await agent.execute(
            SubAgentInput(problem="P", agent_name="tie_breaker", context={"complexity": "simple"}),
            router,
        )
        b = await agent.execute(
            SubAgentInput(problem="P", agent_name="tie_breaker", context={"complexity": "complex"}),
            router,
        )
        return a, b

    a, b = asyncio.run(go())
    assert len(router.calls) == 2
    assert a.result["action"] == "direct"
    assert b.result["action"] == "pipeline"


def test_boundary_key_is_order_insensitive_but_value_sensitive():
    agent = TieBreakerSubAgent()
    k1 = agent._cache_key(SubAgentInput(problem="P", agent_name="t", context={"a": 1, "b": 2}))
    k2 = agent._cache_key(SubAgentInput(problem="P", agent_name="t", context={"b": 2, "a": 1}))
    k3 = agent._cache_key(SubAgentInput(problem="P", agent_name="t", context={"a": 1, "b": 3}))
    assert k1 == k2
    assert k1 != k3


def test_boundary_empty_context_and_unserialisable_context_still_key():
    agent = TieBreakerSubAgent()
    empty = agent._cache_key(SubAgentInput(problem="P", agent_name="t"))
    assert empty == agent._cache_key(SubAgentInput(problem="P", agent_name="t", context={}))
    # default=str keeps a non-JSON value from raising inside the key helper
    assert agent._cache_key(SubAgentInput(problem="P", agent_name="t", context={"o": object()}))


def test_no_regression_identical_input_still_hits_the_cache():
    agent = TieBreakerSubAgent()
    router = _ScriptedRouter(
        ['{"action":"direct","method":null,"confidence":0.9,"rationale":"A"}']
    )
    inp = SubAgentInput(problem="P", agent_name="tie_breaker", context={"complexity": "simple"})

    async def go():
        return await agent.execute(inp, router), await agent.execute(inp, router)

    a, b = asyncio.run(go())
    assert len(router.calls) == 1
    assert a is b
