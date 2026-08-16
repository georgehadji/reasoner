"""MCP server for Reasoner.

Another driving adapter, same as the HTTP layer: it translates MCP tool
calls into the same application-layer calls api/routes/agent.py makes, so a
run started from Claude Desktop is billed, cached, and owned exactly like one
started from curl. Nothing in this package may contain reasoning, routing,
pricing, or aggregation logic -- that all stays in application/services/,
shared with the HTTP adapter.

Requires the optional ``mcp`` extra (``pip install reasoner[mcp]``). Import
this package only where that dependency is expected: mcp_server.py, and the
optional HTTP-transport mount in api/__init__.py behind ENABLE_MCP_HTTP.
"""

from __future__ import annotations


def build_mcp_server():
    """Construct the FastMCP server with every tool registered.

    Raises ImportError with a clear message if the ``mcp`` extra is not
    installed, rather than a bare traceback from a nested import.
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise ImportError(
            "The MCP server requires the 'mcp' package. Install it with "
            "`pip install reasoner[mcp]` (or `pip install mcp>=1.2,<2`)."
        ) from exc

    from reasoner.api.mcp.tools import register_tools

    server = FastMCP(
        name="reasoner",
        instructions=(
            "Delegate judgement calls -- decisions with more than one defensible "
            "answer -- to a multi-model reasoning pipeline. Generators from "
            "different labs propose competing answers, an independent critic "
            "scores them, survivors are stress-tested, and the synthesis labels "
            "every claim VERIFIED, HYPOTHESIS, or UNKNOWN. Do not use it for "
            "lookups, syntax questions, or summarisation -- reasoner_gate will "
            "say so if you are unsure. Runs cost real money and take 20-90s."
        ),
    )
    register_tools(server)
    return server


__all__ = ["build_mcp_server"]
