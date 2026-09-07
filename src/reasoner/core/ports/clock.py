"""Clock port (P3 step 2, docs/plans/root-cause-remediation-2026-09-07.md).

Isolates the one line that reads the OS clock so elapsed-time logic
(rate limiting, circuit breaking, TTL expiry) can be driven by a fake clock
in tests instead of the wall clock -- see D6: a test that needed 80 requests
to arrive faster than a real token bucket refills is not a test of the
bucket, it is a test of the machine it runs on.
"""

from __future__ import annotations

import time
from typing import Protocol


class Clock(Protocol):
    def monotonic(self) -> float: ...

    def time(self) -> float: ...


class SystemClock:
    """Default clock: the real OS clock. Behaviour-neutral default for every caller."""

    def monotonic(self) -> float:
        return time.monotonic()

    def time(self) -> float:
        return time.time()
