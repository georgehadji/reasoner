"""MCP stdio entry-point. Launched as a subprocess by MCP hosts (Claude
Desktop, Claude Code, any client that speaks stdio transport) -- not run
directly by a human. Requires the mcp extra: `pip install reasoner[mcp]`.

Host config:

    {
      "mcpServers": {
        "reasoner": {
          "command": "python",
          "args": ["mcp_server.py"],
          "env": { "REASONER_API_KEY": "rsn_live_..." }
        }
      }
    }
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from reasoner.api.mcp import build_mcp_server

if __name__ == "__main__":
    build_mcp_server().run(transport="stdio")
