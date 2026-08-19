"""
Shared HTTP clients with connection pooling.

The Neuro client lived here: the pipeline reached memory by POSTing to its own
/api/neuro/{recall,learn} over loopback. That is gone -- memory is now called
in-process through core.ports.memory_port, which removed a round-trip per run
and made recall work in CLI/headless mode, where nothing is listening for the
app to call itself. close_neuro_client() remains as a no-op so shutdown paths
that still call it keep working.
"""

from __future__ import annotations


async def close_neuro_client() -> None:
    """No-op. Kept so existing shutdown call sites stay valid."""
    return None
