## 🐛 Bug Report — Failure Propagation Path

### 🔴 CRITICAL (data loss / invisible failures)

**C1 — `_persist_event` bare `except: pass` in `streaming.py` line 133–137**
Every `PIPELINE_FAILED` event in the live SSE path is persisted via this function. A bare `except Exception: pass` means any persistence failure (DB locked, disk full, connection error) produces **zero logs, zero retries, zero dead-letter**. The failure silently vanishes from the event store. The pipeline thinks it persisted; it didn't.
> Fix: replace with `except Exception as exc: logger.warning("Failed to persist event %s: %s", event.event_id, exc)` at minimum.

**C2 — EventBus is entirely bypassed in the live SSE path**
`streaming.py` instantiates `ReasonerPipeline` directly (acknowledged in CLAUDE.md as a known violation). This means **every subscriber registered via `event_bus.subscribe()` never fires for live runs** — audit service, read-model projections via CQRS, WebSocket notifiers, metrics — all dead. Only `_persist_event` runs. Any new feature built on EventBus subscriptions will silently not work in production.

---

### 🟠 HIGH (silent failures, stuck UI)

**H1 — Frontend `isStreaming` stuck `true` forever on network drop**
`sse-reader.ts`: if the backend crashes or a proxy drops the connection mid-stream, `reader.read()` returns `{ done: true }` and `readSSEStream` returns **normally**. `handleSubmit`'s `finally` sets `running: false` in Zustand (re-enabling the Composer), but the assistant message's `isStreaming` is **never set to `false`**. The message stays in the streaming skeleton UI state indefinitely until a page refresh.
> Fix: in `handleSubmit`'s `finally` block, unconditionally dispatch `UPDATE_MESSAGE` with `{ isStreaming: false }` on the active message.

**H2 — EventBus worker task crash is invisible**
`bus.py` line 99: `asyncio.create_task(_queue_worker())` with no `add_done_callback`. If the worker dies unexpectedly, `self._running` stays `True`, `publish()` keeps enqueuing, the queue fills to 1000, and **all subsequent events are silently dropped** (Issue H3 below) with the caller having no idea.
> Fix: `self._worker_task.add_done_callback(self._on_worker_exit)` where the callback sets `self._running = False` and logs `CRITICAL`.

**H3 — EventBus drops events silently when queue is full**
`bus.py` line 147–148: `QueueFull` is caught, logged at `ERROR`, and the event is **discarded** with no dead-letter entry and no back-pressure to the caller. During a burst (e.g., many parallel HyperGate sub-agents completing), `PIPELINE_FAILED` can be dropped here with the caller receiving a normal return.
> Fix: write to the dead-letter JSONL file on `QueueFull` (same path as `_safe_execute` exhaustion).

**H4 — Outer exception path emits `done` without a preceding `error` event**
`streaming.py` lines 1002–1006: when the outermost `except Exception` fires (catastrophic failure), the stream emits only `{"type": "done", "errors": [...]}`. The frontend's `done` handler renders this as a partially-successful run (completed phases shown as successes) with a quiet error bubble — the same UI as a soft warning. **A catastrophic failure looks the same as a non-fatal phase skip.**
> Fix: emit an explicit `{"type": "error", ...}` event before the `done` in the outer except block.

**H5 — `_ser_3` (Jury/critique) uses bare attribute access on `CriticScore` objects**
`serializers.py` lines 398–413: `cs.critic_id`, `cs.critic_model`, `cs.candidate_scores.items()`, `cs.ranking`, `cs.dissenting_note` — all direct attribute access, no `_get_v()` guard, no try/except. After a `--resume` from a state file where `CriticScore` was serialized as a dict, every Jury-preset run will throw `AttributeError` here, terminating the stream mid-phase.
> Fix: wrap in `_get_v(cs, 'critic_id')` etc., or add a `try/except AttributeError` around the block.

---

### 🟡 MEDIUM (degraded behaviour, latent corruption)

**M1 — `task_done()` not called in `_queue_worker` except branch**
`bus.py` line 119: `task_done()` is only called on the clean path. Any future code calling `await queue.join()` to drain the queue would deadlock permanently. Straightforward fix: move `task_done()` into a `finally` block.

**M2 — Subscriber failures after retry exhaustion never reach the pipeline**
`bus.py` lines 159–206: after 3 retries, subscriber errors are written to dead-letter and the function returns normally. A permanently-broken subscriber (e.g., a dead WebSocket handler) retries on every event, logs `ERROR` 3× per event, and the pipeline never learns it's misfiring.

**M3 — `state.phase_tokens` accessed directly across all serializers**
All `_ser_*` functions call `state.phase_tokens.get(...)` or `.values()` without guarding against `None`. This is safe for normal runs but will raise `AttributeError` on `--resume` from a corrupt/partial state file that deserialized `phase_tokens` as `None`.

**M4 — `done` handler overwrites error message content**
If the backend emits `error` then `done` with an empty `phases` array, the `done` handler calls `buildMarkdownFromPhases([])` → `""`, **overwriting the assistant message content** that existed before the error event. The error bubble (a separate message) survives, but the assistant message goes blank.

---

### 🔵 ARCHITECTURE NOTE

**A1 — New `EventType` additions are silently dropped everywhere**
Every dispatch site (`PipelineAggregate._apply_event`, `EventStore._update_aggregate`, `track_pipeline_metrics`, etc.) uses open-ended `if/elif` chains with **no `else` branch**. Adding a new `EventType` without updating every dispatch site produces no error, no warning, and no test failure — the event is published, stored as `"generic"`, and silently ignored by all aggregates and projections. The only place that loudly fails is `_deserialize_event` — but only when trying to *read* a type that was *renamed after* data was stored.
> Recommendation: add `else: logger.warning("Unhandled event type: %s", type(event).__name__)` to every `_apply_event` chain, and consider `match event.event_type: case _: raise NotImplementedError` in aggregate apply methods during development.

---

### Priority order to fix

| # | Location | Severity | Effort |
|---|---|---|---|
| C1 | `streaming.py:133` `_persist_event` bare except | 🔴 Critical | 1 line |
| H1 | `sse-reader.ts` / `chat/page.tsx` `isStreaming` stuck | 🟠 High | ~5 lines |
| H4 | `streaming.py:1002` outer except — emit `error` before `done` | 🟠 High | ~3 lines |
| H2 | `bus.py:99` add `done_callback` to worker task | 🟠 High | ~5 lines |
| H3 | `bus.py:147` `QueueFull` → dead-letter not discard | 🟠 High | ~5 lines |
| H5 | `serializers.py:398` `_ser_3` bare attribute access | 🟠 High | ~10 lines |
| M1 | `bus.py:119` `task_done()` into `finally` | 🟡 Medium | 2 lines |
| M3 | All `_ser_*` guard `phase_tokens` for `None` | 🟡 Medium | ~10 lines |
| C2 | `streaming.py` architectural bypass of EventBus | 🔴 Critical | Large refactor |

Want me to fix any of these? I'd suggest starting with C1, H1, H4, and M1 — they're all under 5 lines each and eliminate the worst invisible failure modes.