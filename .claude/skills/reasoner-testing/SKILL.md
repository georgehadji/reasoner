---
name: reasoner-testing
description: Testing patterns for the Reasoner project — pytest marks, PYTHONPATH setup, async patterns, mocking ProviderRouter, and how to run subsets of the 100+ test suite.
trigger: /reasoner-testing
---

# Reasoner Testing Reference

## Running tests

**Always specify the tests/ directory explicitly:**

```bash
# From the repo root — works
PYTHONPATH=src pytest tests/ -v

# From the repo root without specifying tests/ — collects 0 tests (conftest not found)
pytest        # DON'T do this
```

The `src` prefix on PYTHONPATH is critical. The package is `reasoner` inside `src/`, so:

```bash
# Correct
PYTHONPATH=src pytest tests/ -v

# Wrong — imports fail with ModuleNotFoundError
PYTHONPATH=src/reasoner pytest tests/ -v
```

## Pytest marks

| Mark | Meaning | When to use |
|------|---------|-------------|
| `@pytest.mark.slow` | Takes > 5 seconds | Real LLM calls, large fixture setup |
| `@pytest.mark.integration` | Touches real I/O | Database, file system, external APIs |
| `@pytest.mark.searxng` | Requires live SearXNG | Run only with Docker SearXNG up |
| `@pytest.mark.asyncio` | Async test function | Required for any `async def test_*` |

**Typical CI run (fast, no external deps):**
```bash
PYTHONPATH=src pytest tests/ -v -m "not slow and not integration and not searxng"
```

**Full suite including integration (local only):**
```bash
PYTHONPATH=src pytest tests/ -v --run-slow
```

**Just SearXNG tests (requires `docker-compose.searxng.yml up -d`):**
```bash
PYTHONPATH=src pytest tests/ -m searxng -v --timeout=120
```

## Async test pattern

All async tests need `pytest-asyncio` and the mark:

```python
import pytest
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_something_async():
    mock_llm = AsyncMock(return_value="mocked response")
    result = await some_async_function(llm=mock_llm)
    assert result == "expected"
```

## Mocking LLM providers

The standard pattern for mocking an LLM call in pipeline tests:

```python
from unittest.mock import AsyncMock, MagicMock, patch
from reasoner.infrastructure.llm.ports import LLMResponse

def make_mock_provider(response_text: str) -> MagicMock:
    provider = MagicMock()
    provider.complete = AsyncMock(return_value=LLMResponse(
        content=response_text,
        model="mock-model",
        usage={"prompt_tokens": 10, "completion_tokens": 20},
        cost_usd=0.0,
    ))
    return provider
```

Then patch the router:

```python
@pytest.mark.asyncio
async def test_phase_0_classification(mock_preset):
    from reasoner.pipeline import ReasonerPipeline

    with patch.object(ReasonerPipeline, "_get_provider") as mock_get:
        mock_get.return_value = make_mock_provider('{"task_type": "analytical"}')
        pipeline = ReasonerPipeline(preset=mock_preset)
        state = await pipeline._run_phase_0(state)
        assert state.task_type is not None
```

## Mocking ProviderRouter

```python
from unittest.mock import MagicMock, AsyncMock
from reasoner.infrastructure.llm.router import ProviderRouter

def make_mock_router(responses: dict[str, str]) -> MagicMock:
    """responses maps routing_key → response text"""
    router = MagicMock(spec=ProviderRouter)
    async def mock_complete(role, messages, **kwargs):
        from reasoner.infrastructure.llm.ports import LLMResponse
        text = responses.get(role, "{}")
        return LLMResponse(content=text, model="mock", usage={}, cost_usd=0.0)
    router.complete = mock_complete
    return router
```

## Test file naming

Mirror the source layout:

| Source file | Test file |
|-------------|-----------|
| `src/reasoner/circuit_breaker.py` | `tests/test_circuit_breaker.py` |
| `src/reasoner/hypergate/hyperagent.py` | `tests/test_hypergate.py` |
| `src/reasoner/infrastructure/llm/router.py` | `tests/test_provider_router_degradation.py` |
| `src/reasoner/api/routes/widgets.py` | `tests/test_api_widget_execute.py` |

For regression bugs, use `tests/unit/test_regression_BUG<NNN>.py`.

## Coverage

```bash
PYTHONPATH=src pytest tests/ \
  -m "not slow and not integration and not searxng" \
  --cov=src/reasoner \
  --cov-report=term-missing \
  --cov-report=html
```

Gates (from `self-healing-ci.yml`):
- **60%** — hard CI fail
- **80%** — warning
- **80%+** — target

## Common fixture patterns

```python
import pytest
from dataclasses import replace

@pytest.fixture
def minimal_state():
    from reasoner.domain.pipeline_state import PipelineState
    return PipelineState(problem="test problem")

@pytest.fixture
def mock_preset():
    from reasoner.domain.preset_registry import _PRESET_CONFIGS
    from reasoner.domain.preset_core import PipelinePreset
    cfg = next(c for c in _PRESET_CONFIGS if c["id"] == "multi-perspective-budget")
    return PipelinePreset(**cfg)
```

## Testing the HyperGate

```python
@pytest.mark.asyncio
async def test_hypergate_routes_to_pipeline():
    from reasoner.hypergate import HyperGateAgent
    from reasoner.hypergate.models import HyperContext
    from unittest.mock import AsyncMock

    agent = HyperGateAgent.__new__(HyperGateAgent)
    # Patch sub-agents to return predictable signals
    with patch.object(agent, "_run_sub_agents", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = HyperContext(
            action="pipeline",
            method="debate",
            confidence=0.9,
        )
        result = await agent.route("Is X better than Y?")
        assert result.action == "pipeline"
        assert result.method == "debate"
```

## Parsing — always use extract_json

Never call `json.loads()` directly on LLM output in production code. In tests, verify the parsing layer:

```python
def test_extract_json_handles_markdown_fences():
    from reasoner.parsing import extract_json
    raw = '```json\n{"key": "value"}\n```'
    result = extract_json(raw)
    assert result == {"key": "value"}
```
