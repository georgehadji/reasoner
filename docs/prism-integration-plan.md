# Prism Integration Plan

**Prism** is the internal codename for the open-source iterative search engine at
`Vane-master/Vane-master/` (MIT license, v1.12.1). This document describes how to
integrate its capabilities into Reasoner. Prism remains a standalone Next.js
application; Reasoner remains a Python/FastAPI reasoning pipeline. The goal is to
port Prism's strongest research-loop patterns into Reasoner while retiring overlap.

---

## 1. What Prism Contributes

| Prism capability | Reasoner today | Gap |
|-----------------|---------------|-----|
| Iterative tool-calling researcher (2/6/25 iters) | `run_research_web_search_phase` — 3 LLM-planned iterations, single-shot queries | Deeper adaptive refinement, up to 25 iterations |
| Query classifier (7 flags + standalone reformulation) | HyperGate `WebSearchDetector` — coarse yes/no | Fine-grained: academic, social, skip, widget triggers |
| Citation deduplication pipeline | `SourceAdded` events per result, no synthesis grouping | Structured citation block surfaced in Phase 5 |
| Academic / social / discussion search paths | `SourceType` port exists but only `"general"` used | Activate existing `"academic"` / `"social"` source types |
| File-grounded research (`uploadsSearch` action) | `infrastructure/uploader.py` stores file text, not searched during research phases | Connect existing uploads to researcher tool loop |
| Widget system | Duplicate implementation (weather/stock/calc) | Widget unification: Prism defers to Reasoner API |

**Not porting from Prism:**
- File upload API/storage — already exists at `POST /api/upload` (`api/routes/uploads.py` + `infrastructure/uploader.py`)
- Embedding model abstraction — Neuro L1/L2/L3 handles this
- LLM provider abstraction — Reasoner uses `LLMPort` / `ProviderRouter`
- DB persistence — SQLite event store handles this
- Widget implementations — Reasoner's widget executor is already complete

---

## 2. Architecture Alignment

### 2.1 Dependency Rule

```
Domain/Core  ←  Application  ←  Infrastructure  ←  API
```

Every proposed change must respect this. Concretely:

- **New ports go in `core/ports/`** — `search_port.py` already exists.
  `PrismFileSearchPort` (for searching uploaded file chunks by embedding) belongs there.
- **Implementations go in `infrastructure/`** — The concrete `DiscoveryClient` that
  `PrismResearcher` delegates to lives in `infrastructure/search/discovery.py`.
  Application code must depend on `SearchServicePort`, not `DiscoveryClient` directly.
- **Phase functions live in `application/flows/`** — not a "mixins/" directory (which
  does not exist). Each method's phase logic is in
  `application/flows/<method>_phases.py`.
- **Workflow strategies implement `WorkflowStrategy`** in `application/flows/base.py`.

### 2.2 State Access Patterns

`PipelineState` is composed of sub-objects since the v3 refactor:

```python
# WRONG (flat access, v2 style):
state.web_discovery_results
state.method_state["prism"]

# CORRECT (sub-object access):
state.remainder.web_discovery_results
state.method_state.get("prism")          # returns {} if absent
state.method_state.set("prism", {...})   # always use .set(), never dict assign
```

All Prism method state lives under the `"prism"` key in `MethodState.data`:
```python
{
    "classification": { "skip_search": bool, "academic_search": bool, ... },
    "citations": [{"url": str, "title": str, "snippet": str, "source_type": str}],
    "file_ids": [str],          # populated at request time from uploaded files
    "iteration_log": [str],     # search queries per iteration (for UI progress feed)
}
```

### 2.3 Event Type Pattern

New domain events require three co-located changes in
`src/reasoner/core/events/domain_events.py`:

```python
# Step 1: Add enum value to PipelineEventType
class PipelineEventType(str, Enum):
    ...
    RESEARCH_STEP_EMITTED = "research_step_emitted"   # per-iteration progress
    RESEARCH_CITATIONS_READY = "research_citations_ready"   # final citation bundle

# Step 2: Create frozen dataclass subclassing DomainEvent
@dataclass(frozen=True)
class ResearchStepEmitted(DomainEvent):
    """Single iteration progress: queries fired, reasoning, URLs read."""
    step_type: str = ""      # "searching" | "reasoning" | "reading"
    queries: tuple[str, ...] = field(default_factory=tuple)
    plan: str = ""
    urls: tuple[str, ...] = field(default_factory=tuple)

@dataclass(frozen=True)
class ResearchCitationsReady(DomainEvent):
    """All citations resolved at end of PrismResearcher loop."""
    citation_count: int = 0
    source_types: tuple[str, ...] = field(default_factory=tuple)   # for metrics

# Step 3: Register in both split registries
PIPELINE_EVENT_CLASSES: dict[PipelineEventType, type[DomainEvent]] = {
    ...
    PipelineEventType.RESEARCH_STEP_EMITTED: ResearchStepEmitted,
    PipelineEventType.RESEARCH_CITATIONS_READY: ResearchCitationsReady,
}
```

**Note:** Individual citations should be emitted via the existing `SourceAdded` event
(`PipelineEventType.SOURCE_ADDED`) which already has `url`, `title`, `source_type`,
`relevance_score`. Do not create a separate `SourceBlockEvent`.

### 2.4 Routing Roles

`PrismClassifier` needs an LLM call. Add its routing role to `_KNOWN_ROUTING_ROLES`
in `src/reasoner/domain/preset_core.py`:

```python
_KNOWN_ROUTING_ROLES: frozenset[str] = frozenset({
    ...
    "prism_classify",    # lightweight classification call
})
```

Then the classifier call flows through `WorkflowServices.call_llm(role="prism_classify", ...)`,
which routes through the existing `ProviderRouter` — no new infrastructure needed.

---

## 3. Components to Build

### 3.1 PrismClassifier

**File:** `src/reasoner/application/services/prism_classifier.py`

Ports Prism's `classifier.ts`. Makes one LLM call via `WorkflowServices.call_llm`
(role `"prism_classify"`) and populates `method_state["prism"]["classification"]`.

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from reasoner.application.flows.base import WorkflowServices
    from reasoner.domain.pipeline_state import PipelineState


@dataclass(frozen=True)
class PrismClassification:
    skip_search: bool
    personal_search: bool
    academic_search: bool
    discussion_search: bool
    show_weather_widget: bool
    show_stock_widget: bool
    show_calculation_widget: bool
    standalone_follow_up: str


async def classify_query(
    problem: str,
    services: WorkflowServices,
    state: PipelineState,
) -> PrismClassification:
    """Classify a query via a cheap LLM call.

    Returns a PrismClassification without mutating state — caller decides
    whether to store it in method_state["prism"].
    """
    from reasoner.parsing import extract_json
    raw, _ = await services.call_llm(
        role="prism_classify",
        phase_key="prism_classify",
        system_prompt=_CLASSIFY_SYSTEM,
        user_prompt=problem,
        state=state,
        max_tokens=256,
    )
    data = extract_json(raw) or {}
    cls = data.get("classification", {})
    return PrismClassification(
        skip_search=bool(cls.get("skipSearch", False)),
        personal_search=bool(cls.get("personalSearch", False)),
        academic_search=bool(cls.get("academicSearch", False)),
        discussion_search=bool(cls.get("discussionSearch", False)),
        show_weather_widget=bool(cls.get("showWeatherWidget", False)),
        show_stock_widget=bool(cls.get("showStockWidget", False)),
        show_calculation_widget=bool(cls.get("showCalculationWidget", False)),
        standalone_follow_up=str(data.get("standaloneFollowUp", problem)),
    )
```

`_CLASSIFY_SYSTEM` is a module-level constant in the same file (not in `phases/`
since this is infrastructure-adjacent logic tied to Prism's schema, not a
reasoning phase prompt).

**Wiring:** Called at the start of `run_research_web_search_phase` in
`application/flows/research_phases.py`, and optionally at the end of HyperGate's
web-search detection path for all methods that involve web search.

### 3.2 PrismResearcher

**File:** `src/reasoner/application/flows/prism_research.py`

This is a phase-function module that **replaces** the body of
`run_research_web_search_phase`. The existing function in `research_phases.py` is
kept as a fallback but gated by `settings.PRISM_RESEARCHER_ENABLED`.

```python
"""Iterative tool-calling researcher — Prism logic ported to Python."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Literal

from reasoner.core.ports.search_port import SearchServicePort, SourceType
from reasoner.domain.pipeline_state import PipelineState
from reasoner.application.flows.base import WorkflowServices
from reasoner.parsing import extract_json, ParseError

logger = logging.getLogger(__name__)

ResearchMode = Literal["speed", "balanced", "quality"]
_MODE_MAX_ITERS: dict[ResearchMode, int] = {"speed": 2, "balanced": 6, "quality": 25}


@dataclass
class _Citation:
    url: str
    title: str
    snippet: str
    source_type: str   # "web" | "academic" | "discussion" | "file" | "scraped"


async def run_prism_research_phase(
    state: PipelineState,
    services: WorkflowServices,
    search_client: SearchServicePort,
    mode: ResearchMode = "balanced",
) -> None:
    """Iterative researcher loop: plan → search → refine → done."""
    ...
```

Key design decisions:
- **`search_client: SearchServicePort`** is injected, not imported from infrastructure.
  The caller (phase runner in `pipeline_flow.py`) injects the concrete client.
  This respects the hexagonal dependency rule.
- **Actions** (web search, academic search, scrape, uploads search, done) are
  registered as `dict[str, Callable]` within the module — no separate `ActionRegistry`
  class needed. Prism's class hierarchy is overengineering for a Python context where
  `async def` functions are already first-class.
- **Academic search** = call `search_client.search(query, source_type="academic")`.
  The `SourceType` port already supports this. No new client needed.
- **Discussion search** = `search_client.search(query, source_type="social")`.
- **Scrape action** = call existing `reasoner.scraper.scrape_urls([url])`.
- **Uploads search** = inject a `FileSearchPort` (see §3.3); skip gracefully if no
  files uploaded.
- **Deduplication** by normalised URL via existing `_normalize_url` from
  `reasoner.core.search`.
- **Per-iteration events:** emit `ResearchStepEmitted` and `SourceAdded` events via
  the event bus (accessible from `services`). Do not call the event bus directly
  — follow the pattern in `search_phases.py` where `services.log()` handles all
  structured output.
- **Citations in state:** after the loop, store deduplicated citations in
  `state.method_state.set("prism", {**state.method_state.get("prism"), "citations": [...]})`.

### 3.3 FileSearchPort + Implementation

Prism's `uploadsSearch` action needs to search uploaded file chunks by semantic
similarity. Reasoner already stores uploaded files in `infrastructure/uploader.py`
but has no embedding-search path. This requires:

**Port:** `src/reasoner/core/ports/file_search_port.py`

```python
"""Port for semantic search over uploaded file chunks."""

from __future__ import annotations
from typing import Any, Protocol


@dataclass(frozen=True)
class FileChunk:
    file_id: str
    content: str
    score: float


class FileSearchPort(Protocol):
    async def search_chunks(
        self,
        file_ids: list[str],
        query: str,
        top_k: int = 5,
    ) -> list[FileChunk]: ...
```

**Implementation:** `src/reasoner/infrastructure/prism/file_search.py`

Uses the existing `infrastructure/uploader.py` storage layout. Computes cosine
similarity against stored embeddings (generated at upload time by Neuro's embedding
model — requires a one-time indexing pass for pre-existing files).

This is the only genuinely new infrastructure component. Keep it simple:
- Read chunk JSON from the path recorded in `uploader.py`'s file record
- Embed the query via the Neuro embedding client
- Sort by cosine similarity, return top-k

**Important:** The `FileSearchPort` is passed as an optional dependency to
`run_prism_research_phase`. If `file_ids` is empty or no embedding model is
configured, the `uploads_search` action is silently disabled — identical to
Prism's `enabled()` predicate.

### 3.4 Citation Pipeline in Synthesis

**File:** `src/reasoner/phases/_shared.py`

The shared synthesis prompt builder already injects `vetted_context` into Phase 5.
Extend the injection to also include Prism citations when present:

```python
def build_synthesis_context(state: PipelineState) -> str:
    parts = []
    # ... existing vetted_context injection ...
    
    # Prism citations (populated by PrismResearcher)
    prism = state.method_state.get("prism")
    citations = prism.get("citations", [])
    if citations:
        parts.append("[SOURCED EVIDENCE]")
        for i, c in enumerate(citations, 1):
            parts.append(f"[{i}] {c['title']} — {c['url']}\n    {c['snippet']}")
        parts.append(
            "\nWhen making a claim supported by the above sources, "
            "append [N] inline. Include a ## Sources section at the end."
        )
    return "\n\n".join(parts)
```

The synthesis prompts in `phases/_shared.py` already call a context-builder. Extend
that builder — do not modify all 17 method-specific prompt files individually.

**Serializer:** `src/reasoner/application/services/serializers.py` (not the shim at
`api/serializers.py`) — add a `_ser_citations` helper and call it inside `_ser_5`:

```python
def _ser_citations(state: PipelineState) -> list[dict]:
    prism = state.method_state.get("prism") if state.method_state else {}
    return prism.get("citations", [])

def _ser_5(state: PipelineState) -> dict:
    base = {...}   # existing synthesis fields
    citations = _ser_citations(state)
    if citations:
        base["citations"] = citations
    return base
```

---

## 4. Where PrismResearcher Plugs In

### 4.1 Research Method (primary target)

`src/reasoner/application/flows/research_phases.py` — `run_research_web_search_phase`:

```python
async def run_research_web_search_phase(
    state: PipelineState,
    services: WorkflowServices,
    domain: str | None = None,
) -> None:
    from reasoner.core.settings import settings
    if settings.PRISM_RESEARCHER_ENABLED:
        from reasoner.application.flows.prism_research import run_prism_research_phase
        from reasoner.infrastructure.search.discovery import get_discovery_client
        client, _ = await get_discovery_client()
        await run_prism_research_phase(state, services, client, mode="quality")
        # Backfill remainder.web_discovery_results from citations for downstream
        # phases that still consume vetted_context
        prism = state.method_state.get("prism")
        state.remainder.web_discovery_results = [
            {"url": c["url"], "title": c["title"], "snippet": c["snippet"]}
            for c in prism.get("citations", [])
        ]
        return
    # existing loop (3 iterations, unchanged) below
    ...
```

The existing 3-iteration loop is kept intact as the fallback. The feature flag
`PRISM_RESEARCHER_ENABLED` in `core/settings.py` defaults to `False` until validated.

### 4.2 Other Methods (optional "speed" mode)

Methods that call `run_context_vetting_phase` in `search_phases.py` can optionally
run a 2-iteration "speed" Prism pass before vetting. This is **Phase 4 work**, not
Phase 2. Keep scope tight — don't wire all 17 methods at once.

### 4.3 HyperGate Classifier Integration

The `WebSearchDetector` sub-agent in `hypergate/sub_agents/` returns `needs_web=True/False`.
When `True`, run `classify_query()` before HyperGate returns. Store the result in
`state.method_state.set("prism", {"classification": classification_dict})`.

This enrichment allows:
- Correct `source_type` passed to `DiscoveryClient` (academic vs general)
- Widget triggers propagated to existing `WidgetExecutor` dispatch
- `standaloneFollowUp` used as the search query instead of the raw problem

**Implementation:** add to `src/reasoner/hypergate/hyperagent.py` after the
TieBreaker resolves and before returning — one `await classify_query(...)` call
if `web_search_needed`.

---

## 5. Widget Unification

### 5.1 Reasoner's Widget System

Reasoner already has `WidgetExecutor` with weather, stock, and calculation widgets
wired in `api/routes/widgets.py`. These map 1:1 to Prism's three widgets.

### 5.2 Prism Standalone Change

Add a `REASONER_API` environment variable to Prism's config
(`Vane-master/Vane-master/src/lib/config/index.ts`). When set, Prism's widget
components (client-side) call Reasoner's REST endpoints instead of local handlers:

- Weather: `GET {REASONER_API}/api/widget/weather?location=...`
- Stock: `GET {REASONER_API}/api/widget/stock?symbol=...`
- Calculation: `POST {REASONER_API}/api/widget/calculate`

Verify these exact paths exist in `api/routes/widgets.py` before wiring. If the
paths differ, adjust Prism — not Reasoner.

Remove widget _implementation_ code from `Vane-master/src/lib/agents/search/widgets/`
only after verifying the Reasoner endpoints respond correctly in integration testing.

---

## 6. New Domain Events (Concrete Implementation)

**File:** `src/reasoner/core/events/domain_events.py`

```python
# ── Additions to PipelineEventType enum ──────────────────────────────────
RESEARCH_STEP_EMITTED = "research_step_emitted"
RESEARCH_CITATIONS_READY = "research_citations_ready"

# ── New frozen dataclasses ────────────────────────────────────────────────
@dataclass(frozen=True)
class ResearchStepEmitted(DomainEvent):
    """Single iteration progress event from PrismResearcher loop."""
    step_type: str = ""       # "searching" | "reasoning" | "reading"
    queries: tuple[str, ...] = field(default_factory=tuple)
    plan: str = ""
    urls: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ResearchCitationsReady(DomainEvent):
    """Emitted once when PrismResearcher completes and citations are stored."""
    citation_count: int = 0

# ── Register in split registries ─────────────────────────────────────────
PIPELINE_EVENT_CLASSES: dict[PipelineEventType, type[DomainEvent]] = {
    ...
    PipelineEventType.RESEARCH_STEP_EMITTED: ResearchStepEmitted,
    PipelineEventType.RESEARCH_CITATIONS_READY: ResearchCitationsReady,
}
# Also add to EVENT_CLASSES (the combined dict).
```

Individual citation URLs are emitted as existing `SourceAdded` events
(`PipelineEventType.SOURCE_ADDED`) — no new event class needed for those.

---

## 7. Settings

**File:** `src/reasoner/core/settings.py`

```python
# ── Prism integration ──
PRISM_RESEARCHER_ENABLED: bool = os.getenv("PRISM_RESEARCHER_ENABLED", "false").lower() in ("1", "true", "yes")
PRISM_CLASSIFIER_ENABLED: bool = os.getenv("PRISM_CLASSIFIER_ENABLED", "false").lower() in ("1", "true", "yes")
PRISM_FILE_SEARCH_ENABLED: bool = os.getenv("PRISM_FILE_SEARCH_ENABLED", "false").lower() in ("1", "true", "yes")
```

All three default to `False`. Each maps to a specific phase in the build order.

---

## 8. Frontend Additions (ui-next)

### 8.1 ResearchProgress Component

**`ui-next/src/components/phases/ResearchProgress.tsx`**

Renders `research_step_emitted` SSE events as a live activity feed inside the Phase 2
card. This is the most visible UX improvement — today Reasoner shows a spinner; after
this phase users see:

```
  Research  [live]
  ──────────────────────────────────────────
  Searching: "AI sentencing COMPAS bias", "recidivism disparities study 2024"
  Thinking: "Initial results confirm bias. Narrowing to court rulings..."
  Searching: "state v loomis 2016 COMPAS", "ProPublica recidivism analysis"
  Reading: propublica.org → scholar.google.com → supremecourt.gov
  ✓  7 sources found
```

### 8.2 SourceCard Component

**`ui-next/src/components/phases/SourceCard.tsx`**

Renders the `citations` array in `_ser_5` output as a scrollable chip strip at the
bottom of `SynthesisCard.tsx`. Clicking a chip opens the URL. Source type badge:
web / academic / discussion / file / scraped.

### 8.3 Composer File Integration

The file upload UI already exists via the upload API (`POST /api/upload`). The
Composer component needs to:
1. Store returned `file_id` values in `appStore` (Zustand).
2. Include `file_ids: string[]` in the `POST /api/pipelines` request body — the
   pipeline_service reads this and sets `method_state["prism"]["file_ids"]` before
   running phases.

This is a **data-flow change only** — no new upload API needed.

### 8.4 SSE Event Type Updates

**`ui-next/src/hooks/usePipelineStream.ts`** and **`ui-next/src/lib/types.ts`**:

```typescript
export interface ResearchStepEvent {
  step_type: "searching" | "reasoning" | "reading"
  queries: string[]
  plan: string
  urls: string[]
}

export interface Citation {
  url: string
  title: string
  snippet: string
  source_type: "web" | "academic" | "discussion" | "file" | "scraped"
}
```

---

## 9. File Inventory

### New Python files

| File | Purpose | Note |
|------|---------|------|
| `src/reasoner/application/services/prism_classifier.py` | Query classification | Depends on `WorkflowServices` protocol |
| `src/reasoner/application/flows/prism_research.py` | Iterative researcher loop | Phase function, not a class |
| `src/reasoner/core/ports/file_search_port.py` | Port for file chunk search | Core layer — no imports from infra |
| `src/reasoner/infrastructure/prism/__init__.py` | Package marker | |
| `src/reasoner/infrastructure/prism/file_search.py` | FileSearchPort implementation | Reads from existing uploader storage |
| `tests/unit/test_prism_classifier.py` | Classifier unit tests | |
| `tests/unit/test_prism_research.py` | Researcher loop unit tests | |
| `tests/unit/test_file_search.py` | FileSearch implementation tests | |

### Modified Python files

| File | Change |
|------|--------|
| `src/reasoner/core/events/domain_events.py` | Add 2 enum values + 2 frozen dataclasses + registrations |
| `src/reasoner/core/settings.py` | Add 3 feature-flag settings |
| `src/reasoner/domain/preset_core.py` | Add `"prism_classify"` to `_KNOWN_ROUTING_ROLES` |
| `src/reasoner/application/services/serializers.py` | Extend `_ser_5` with optional citations block |
| `src/reasoner/application/flows/research_phases.py` | Wrap existing loop with feature-flag + Prism path |
| `src/reasoner/hypergate/hyperagent.py` | Call `classify_query` after WebSearchDetector when enabled |
| `src/reasoner/phases/_shared.py` | Extend synthesis context builder with citations |

### New frontend files

| File | Purpose |
|------|---------|
| `ui-next/src/components/phases/ResearchProgress.tsx` | Live per-iteration research feed |
| `ui-next/src/components/phases/SourceCard.tsx` | Citation chip strip |

### Modified frontend files

| File | Change |
|------|--------|
| `ui-next/src/hooks/usePipelineStream.ts` | Handle `research_step_emitted` event type |
| `ui-next/src/lib/types.ts` | Add `ResearchStepEvent`, `Citation` interfaces |
| `ui-next/src/components/phases/SynthesisCard.tsx` | Embed `SourceCard` when citations present |
| `ui-next/src/components/layout/Composer.tsx` | Thread `file_ids` from app store into pipeline request |

### Prism-side changes

| File | Change |
|------|--------|
| `Vane-master/Vane-master/src/lib/config/index.ts` | Add `REASONER_API` env var |
| `Vane-master/Vane-master/src/lib/agents/search/widgets/` | Replace local implementations with Reasoner API calls |

---

## 10. Build Order

Each phase is independently deployable and gated by a feature flag.

```
Phase 1 — Foundation (2 days, no feature flags)
│  Add enum values + frozen dataclasses to domain_events.py
│  Add "prism_classify" to _KNOWN_ROUTING_ROLES
│  Add 3 settings to settings.py
│  ✓ All existing tests pass
│
Phase 2 — PrismResearcher (4–5 days, PRISM_RESEARCHER_ENABLED=false)
│  Write prism_research.py + file_search_port.py + infrastructure/prism/file_search.py
│  Unit tests with mocked search_client and file_search
│  Wire feature-flag path in research_phases.py
│  ✓ pytest tests/unit/test_prism_research.py
│
Phase 3 — Citation Pipeline (2 days, depends on Phase 2)
│  Extend _shared.py context builder
│  Extend _ser_5 in application/services/serializers.py
│  Add ResearchProgress + SourceCard to ui-next
│  ✓ Manual: run Research method, verify citations in synthesis output
│
Phase 4 — PrismClassifier (2 days, PRISM_CLASSIFIER_ENABLED=false)
│  Write prism_classifier.py
│  Wire into hypergate/hyperagent.py
│  Unit tests for classifier output parsing
│  ✓ Prompt "weather in Paris" → show_weather_widget=True in method_state
│
Phase 5 — File Search Integration (3 days, PRISM_FILE_SEARCH_ENABLED=false)
│  Implement file_search.py with cosine similarity
│  Wire uploads_search action into prism_research.py
│  Thread file_ids through Composer → pipeline request → method_state
│  ✓ Upload PDF, ask question, citations reference file with source_type="file"
│
Phase 6 — Widget Unification (2 days)
   Verify Reasoner widget endpoint paths match expected calls
   Update Prism's widget components to call Reasoner API
   Remove duplicate widget code from Prism
   ✓ Prism standalone with REASONER_API set shows Reasoner-sourced widgets
```

---

## 11. Anti-Patterns to Avoid

| Pattern | Why wrong | Correct approach |
|---------|-----------|-----------------|
| `from reasoner.infrastructure.search.discovery import DiscoveryClient` inside application layer | Violates hexagonal rule | Inject `SearchServicePort` via parameter |
| `state.method_state["prism"]` | `MethodState.data` not subscriptable directly | Use `state.method_state.get("prism")` and `.set("prism", ...)` |
| `state.web_discovery_results` | Flat access, v2 style | `state.remainder.web_discovery_results` |
| Editing `src/reasoner/api/serializers.py` | That's a backward-compat shim | Edit `src/reasoner/application/services/serializers.py` |
| Creating `src/reasoner/api/routes/uploads.py` | That file already exists | Extend existing `uploads.py` if needed |
| `@dataclass class Foo(DomainEvent): event_type: ClassVar[str]` | Wrong event pattern | `@dataclass(frozen=True)` + enum value + registry entry |
| Adding phase-function logic in `application/mixins/` | That directory does not exist | Add to `application/flows/<method>_phases.py` |
| Separate `ActionRegistry` class | Overengineering for Python | `dict[str, Callable]` with `asyncio.gather` |

---

## 12. Success Criteria

1. Research method with `PRISM_RESEARCHER_ENABLED=true` produces ≥ 3 inline `[N]`
   citations in Phase 5 synthesis and a `## Sources` section.
2. Academic query (e.g., "latest research on transformer attention mechanisms")
   activates `academic_search=True` in `method_state["prism"]["classification"]`.
3. File upload round-trip: upload PDF → run Research preset → answer references
   content from the file with `source_type: "file"` citation.
4. Prism standalone with `REASONER_API=http://localhost:8003` — weather query shows
   weather widget data. No widget code remains in Prism after Phase 6.
5. All existing tests pass at the end of each phase (no regressions).
6. `get_events(from_version=-1)` — existing compaction tests unchanged.
