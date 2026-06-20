# Δομές Δεδομένων Python για Agent Memory

## Εισαγωγή

Η μνήμη ενός AI agent δεν είναι απλά μια λίστα — είναι ένα σύστημα με απαιτήσεις σε **χρονική πρόσβαση**, **χωρητικότητα**, **εύρεση**, και **εκκαθάριση**. Η Python προσφέρει πολλές δομές δεδομένων (στη standard library και σε third-party βιβλιοθήκες) που καλύπτουν διαφορετικά memory patterns.

Το παρακάτω κείμενο διακρίνει τα **abstract data types** (stack, queue, priority queue) από τις **concrete implementations** (`list`, `deque`, `heapq`) και παρουσιάζει κάθε δομή στο πλαίσιο agent memory design.

---

## 1. Βασική Λίστα (`list`) — Append-Only Log

**Τι είναι**: Δυναμικός πίνακας (dynamic array) με amortized O(1) append και O(1) random access.

**Πότε τη χρησιμοποιείς**: Append-only event log, ιστορικό ενεργειών χωρίς ανάγκη αφαίρεσης από την αρχή.

**Προσοχή**: Η `list.pop(0)` είναι O(n) — αν χρειάζεσαι FIFO, χρησιμοποίησε `deque`.

```python
from __future__ import annotations
from datetime import datetime, timezone


class EventLog:
    """Append-only event log με type safety."""

    def __init__(self, max_size: int = 10_000) -> None:
        self._events: list[dict[str, object]] = []
        self._max_size = max_size

    def append(self, event_type: str, data: dict[str, object]) -> None:
        if len(self._events) >= self._max_size:
            # Eviction: αφαίρεσε το παλαιότερο 10%
            cutoff = self._max_size // 10
            self._events = self._events[cutoff:]
        self._events.append({
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "type": event_type,
            "data": data,
        })

    def recent(self, n: int = 10) -> list[dict[str, object]]:
        return self._events[-n:]

    def __len__(self) -> int:
        return len(self._events)
```

---

## 2. `collections.deque` — Sliding Window / Ring Buffer

**Τι είναι**: Double-ended queue με O(1) append/pop **και στις δύο πλευρές**. Υποστηρίζει `maxlen` για αυτόματο bounded memory.

**Πότε τη χρησιμοποιείς**: Short-term memory, sliding window τελευταίων N μηνυμάτων, conversation buffer.

**Γιατί υπερτερεί της `list`**: Η `list.pop(0)` είναι O(n), η `deque.popleft()` είναι O(1).

```python
from collections import deque
from typing import Any


class ConversationBuffer:
    """Bounded sliding window για τα τελευταία N μηνύματα."""

    def __init__(self, max_turns: int = 20) -> None:
        self._buffer: deque[dict[str, Any]] = deque(maxlen=max_turns)

    def add_message(self, role: str, content: str) -> None:
        self._buffer.append({"role": role, "content": content})

    def get_context(self) -> list[dict[str, Any]]:
        """Επιστρέφει αντίγραφο για injection στο LLM prompt."""
        return list(self._buffer)

    @property
    def is_full(self) -> bool:
        return len(self._buffer) == self._buffer.maxlen
```

---

## 3. Stack (LIFO) — Undo/Backtracking

**Τι είναι**: Abstract data type, Last-In-First-Out. Υλοποιείται εύκολα με `list.append()` / `list.pop()`.

**Πότε τη χρησιμοποιείς**: Undo/redo, αναδρομή αποφάσεων, call stack παρακολούθησης.

```python
from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass
class UndoStack(Generic[T]):
    """Type-safe stack με undo capability."""
    _items: list[T] = field(default_factory=list)

    def push(self, item: T) -> None:
        self._items.append(item)

    def pop(self) -> T:
        if not self._items:
            raise IndexError("Undo stack is empty — no actions to revert")
        return self._items.pop()

    def peek(self) -> T:
        if not self._items:
            raise IndexError("Undo stack is empty")
        return self._items[-1]

    @property
    def is_empty(self) -> bool:
        return len(self._items) == 0
```

---

## 4. Queue (FIFO) — Task Pipeline

**Τι είναι**: First-In-First-Out. Για single-threaded agents χρησιμοποίησε `collections.deque`. Για multi-threaded, `queue.Queue` (thread-safe) ή `asyncio.Queue` (async).

**Πότε τη χρησιμοποιείς**: Task pipeline, sequential event processing.

```python
import asyncio
from typing import Any


class AsyncTaskQueue:
    """Async-safe task queue για agent event loops."""

    def __init__(self, max_pending: int = 100) -> None:
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(
            maxsize=max_pending,
        )

    async def enqueue(self, task_type: str, payload: dict[str, Any]) -> None:
        await self._queue.put({"type": task_type, "payload": payload})

    async def dequeue(self) -> dict[str, Any]:
        return await self._queue.get()

    @property
    def pending_count(self) -> int:
        return self._queue.qsize()
```

---

## 5. Priority Queue — Weighted Task Scheduling

**Τι είναι**: Queue όπου τα στοιχεία εξάγονται με βάση προτεραιότητα. Υλοποιείται με `heapq` (min-heap).

**Πότε τη χρησιμοποιείς**: Scheduling agent actions κατά urgency/importance, weighted memory retrieval.

**Προσοχή**: Τα `heapq` dicts δεν είναι comparable — χρησιμοποίησε `dataclass` με `order=True` ή wrapper tuple.

```python
import heapq
from dataclasses import dataclass, field
from typing import Any


@dataclass(order=True)
class PrioritizedTask:
    priority: int
    payload: dict[str, Any] = field(compare=False)


class AgentScheduler:
    """Min-heap scheduler: χαμηλότερο priority = εκτελείται πρώτο."""

    def __init__(self) -> None:
        self._heap: list[PrioritizedTask] = []

    def schedule(self, priority: int, task: dict[str, Any]) -> None:
        heapq.heappush(self._heap, PrioritizedTask(priority, task))

    def next_task(self) -> dict[str, Any]:
        if not self._heap:
            raise IndexError("No tasks scheduled")
        return heapq.heappop(self._heap).payload

    @property
    def is_empty(self) -> bool:
        return len(self._heap) == 0
```

---

## 6. Dictionary / `defaultdict` — Keyed State Store

**Τι είναι**: Hash table με O(1) average lookup/insert. **Δεν είναι λίστα** — είναι associative array.

**Πότε τη χρησιμοποιείς**: Agent state, user preferences, session metadata, entity memory.

```python
from collections import defaultdict
from typing import Any


class EntityMemory:
    """Keyed memory store: ένα dict ανά entity (user, session, topic)."""

    def __init__(self) -> None:
        self._store: defaultdict[str, dict[str, Any]] = defaultdict(dict)

    def set(self, entity_id: str, key: str, value: Any) -> None:
        self._store[entity_id][key] = value

    def get(self, entity_id: str, key: str, default: Any = None) -> Any:
        return self._store[entity_id].get(key, default)

    def get_all(self, entity_id: str) -> dict[str, Any]:
        return dict(self._store[entity_id])

    def forget(self, entity_id: str) -> None:
        self._store.pop(entity_id, None)
```

---

## 7. Time-Series Memory — Timestamped Events με TTL

**Τι είναι**: Λίστα ή deque με timestamps, συνδυασμένη με eviction policy (TTL).

**Πότε τη χρησιμοποιείς**: Temporal reasoning, "τι έγινε τις τελευταίες 5 λεπτά", decay-based memory.

```python
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Any


@dataclass
class TimestampedEvent:
    timestamp: datetime
    event_type: str
    data: dict[str, Any]


class TTLMemory:
    """Memory με αυτόματη εκκαθάριση ληγμένων entries."""

    def __init__(self, ttl: timedelta = timedelta(hours=1)) -> None:
        self._events: list[TimestampedEvent] = []
        self._ttl = ttl

    def add(self, event_type: str, data: dict[str, Any]) -> None:
        self._purge_expired()
        self._events.append(TimestampedEvent(
            timestamp=datetime.now(tz=timezone.utc),
            event_type=event_type,
            data=data,
        ))

    def query(
        self,
        since: timedelta | None = None,
        event_type: str | None = None,
    ) -> list[TimestampedEvent]:
        self._purge_expired()
        results = self._events
        if since is not None:
            cutoff = datetime.now(tz=timezone.utc) - since
            results = [e for e in results if e.timestamp >= cutoff]
        if event_type is not None:
            results = [e for e in results if e.event_type == event_type]
        return results

    def _purge_expired(self) -> None:
        cutoff = datetime.now(tz=timezone.utc) - self._ttl
        self._events = [e for e in self._events if e.timestamp >= cutoff]
```

---

## 8. Tagged / Categorized Memory — `defaultdict[str, list]`

**Τι είναι**: Multi-index memory με κατηγορίες ως κλειδιά.

**Πότε τη χρησιμοποιείς**: Ομαδοποίηση memories κατά τύπο (observations, decisions, errors), γρήγορο filtering.

```python
from collections import defaultdict
from typing import Any


class TaggedMemory:
    """Memories οργανωμένα σε tags/κατηγορίες."""

    def __init__(self) -> None:
        self._store: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)

    def add(self, tag: str, entry: dict[str, Any]) -> None:
        self._store[tag].append(entry)

    def get_by_tag(self, tag: str) -> list[dict[str, Any]]:
        return list(self._store.get(tag, []))

    def all_tags(self) -> list[str]:
        return list(self._store.keys())

    def count(self, tag: str | None = None) -> int:
        if tag is not None:
            return len(self._store.get(tag, []))
        return sum(len(v) for v in self._store.values())
```

---

## Σύνοψη: Πότε χρησιμοποιείς τι

| Ανάγκη | Δομή | Γιατί |
|---|---|---|
| Append-only log | `list` | O(1) append, random access |
| Sliding window (τελευταία N) | `deque(maxlen=N)` | O(1) και στα δύο άκρα, bounded |
| Undo / backtracking | `list` ως stack | O(1) push/pop τέλος |
| Sequential task processing | `deque` ή `asyncio.Queue` | O(1) FIFO, thread/async safe |
| Weighted scheduling | `heapq` | O(log n) insert/extract-min |
| Keyed state (user/session) | `dict` / `defaultdict` | O(1) average lookup |
| Temporal queries + TTL | `list` + timestamp + purge | Time-windowed retrieval |
| Categorized retrieval | `defaultdict[str, list]` | Multi-index grouping |

---

## Τι λείπει (για production agent systems)

Οι παραπάνω δομές καλύπτουν **short-term / working memory**. Για ολοκληρωμένο agent memory σύστημα χρειάζεσαι επίσης:

- **Persistence**: SQLite (`sqlite3`), Redis, ή PostgreSQL για μνήμη που επιβιώνει restarts.
- **Semantic retrieval**: Vector stores (ChromaDB, FAISS, Qdrant) για embedding-based similarity search.
- **Long-term / episodic memory**: Summarization pipelines που συμπυκνώνουν παλιά events σε summaries.
- **Memory hierarchy**: Short-term (deque) → Working (dict) → Long-term (vector DB) → Archival (persistent store).
