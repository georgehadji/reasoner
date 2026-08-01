# Phase 1 Implementation Plan: Immutable Boundaries

## Scope
Introduce immutable `Document`, `Result`, and `Context` types — then wrap existing
phase bodies unchanged inside the new signatures (adapter pattern). The pipeline
runner is updated to use `Result` composition, but every phase's *implementation*
remains identical.

**No behavior change.** All golden-set tests and structural tests must pass unchanged.

## Step 1: Domain Model Types (`domain/core_types.py`)

Add frozen dataclasses alongside existing types:

```python
@dataclass(frozen=True)
class WritingDocument:
    """The article artifact. Immutable — every edit produces a new instance."""
    version: int = 0
    markdown: str = ""
    title: str = ""
    produced_by: str = ""  # phase name that generated this version
    locked_spans: tuple[tuple[int, int], ...] = ()

@dataclass(frozen=True)
class Claim:
    """Atomic verified/reviewed claim extracted from the article."""
    id: str = ""
    text: str = ""
    status: str = "unverified"  # verified | supported | speculative | unsupported
    source_url: str = ""
    note: str = ""
    verified_against_version: int = 0

@dataclass(frozen=True)
class ArticleContext:
    """Immutable context passed through phases. Replaces direct writing_state mutation."""
    problem: str
    language: str = "English"
    preset_name: str = "article-budget"
    content_class: str = "blog"
    
    # Article artifacts (immutable, replaced on each phase boundary)
    doc: WritingDocument = field(default_factory=WritingDocument)
    claims: tuple[Claim, ...] = ()
    sources: tuple[dict, ...] = ()
    source_metadata: tuple[dict, ...] = ()
    outline: tuple[dict, ...] = ()
    argument_map: dict = field(default_factory=dict)
    verification_results: dict = field(default_factory=dict)
    structural_critique: dict = field(default_factory=dict)
    editorial_audit: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    style_brief: dict | None = None
    
    def replace(self, **kwargs) -> ArticleContext:
        return replace(self, **kwargs)
```

## Step 2: Result Type (`domain/core_types.py`)

```python
T = TypeVar("T")
E = TypeVar("E")

@dataclass(frozen=True)
class Ok(Generic[T]):
    value: T
    
@dataclass(frozen=True)
class Err(Generic[E]):
    error: str
    phase: str = ""
    fallback: T | None = None  # degraded context, if available

Result = Union[Ok, Err]
```

## Step 3: Phase Adapter Protocol

```python
PhaseFn = Callable[[ArticleContext, Deps], Result[ArticleContext, str]]
```

Where `Deps` wraps `call_llm`, `log`, `run_phase` etc. — same services as today,
just typed to accept `ArticleContext` instead of `PipelineState`.

## Step 4: Adapter Pattern

Each existing phase fn is wrapped:

```python
# BEFORE (current): mutates state.writing_state in-place
async def run_article_draft_phase(state: PipelineState, services: WorkflowServices) -> None:
    prompt = article_draft_prompt(state)
    response, meta = await services.call_llm("writing_draft", prompt, state)
    data = extract_json(response)
    state.writing_state["final_article"] = data.get("article", "")

# AFTER (Phase 1): adapter wraps the SAME logic, returns Result
def wrap_draft_phase() -> PhaseFn:
    async def fn(ctx: ArticleContext, deps: Deps) -> Result:
        # Build a temporary PipelineState from ArticleContext for the prompt builder
        state = ctx.to_pipeline_state()
        prompt = article_draft_prompt(state)
        try:
            response, meta = await deps.call_llm("writing_draft", prompt, state)
            data = extract_json(response)
            article_text = data.get("article", "") or data.get("humanized_article", "")
            new_ctx = ctx.replace(
                doc=ctx.doc.replace(
                    version=ctx.doc.version + 1,
                    markdown=article_text,
                    produced_by="draft"
                )
            )
            return Ok(new_ctx)
        except Exception as e:
            return Err(str(e), phase="draft", fallback=ctx)
    return fn
```

## Step 5: Pipeline Combinator

```python
def pipeline(*phases: PhaseFn) -> PhaseFn:
    async def run(ctx: ArticleContext, deps: Deps) -> Result:
        cur = ctx
        for phase in phases:
            result = await phase(cur, deps)
            match result:
                case Ok(new_ctx):
                    cur = new_ctx
                case Err() if result.fallback is not None:
                    cur = result.fallback
                case Err():
                    return result
        return Ok(cur)
    return run
```

## Step 6: Serializer Update

Serializers currently read `state.writing_state` via `_get_v()`. For Phase 1,
they also accept `ArticleContext` (reading from the frozen fields). A thin bridge
function converts `ArticleContext` → dict matching the `_get_v()`-accessible shape.

## Step 7: Bridge to PipelineState

For backward compatibility (serializers, prompt builders, existing tests that
construct PipelineState directly), `ArticleContext` has a `to_pipeline_state()`
method that reconstructs what the old system expects.

## Rollback

Keep the old `ArticleFlow.execute()` behind a flag. The new `execute_with_context()`
runs alongside it. Default: old path. Opt-in: new path via env var or preset flag.
