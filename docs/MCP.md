# MCP Server

Reasoner ships an [MCP](https://modelcontextprotocol.io) server so it can be added to Claude Desktop, Claude Code, or any MCP-speaking host as a tool provider — no HTTP client code required.

It is another driving adapter, same tier as the REST API: an MCP tool call runs through the identical application-layer path as `POST /api/agent/run` — same auth resolution, same idempotency guard, same credit metering, same pipeline ownership record. A run started from Claude Desktop is billed exactly like one started from curl.

---

## Install

The MCP server needs the optional `mcp` extra:

```bash
pip install reasoner[mcp]
```

(or `pip install -e ".[mcp]"` from a source checkout, or `pip install mcp>=1.2,<2` directly if you manage dependencies yourself).

## Run it

### stdio (Claude Desktop, Claude Code, most hosts)

Add to your host's MCP config:

```json
{
  "mcpServers": {
    "reasoner": {
      "command": "python",
      "args": ["mcp_server.py"],
      "env": { "REASONER_API_KEY": "rsn_live_..." }
    }
  }
}
```

`args` should point at `mcp_server.py` in your Reasoner checkout — use an absolute path if the host's working directory won't be the repo root. The host launches this as a subprocess and talks to it over stdin/stdout; there is no network exposure.

`REASONER_API_KEY` is required for the metered tools (`reasoner_run`, `reasoner_followup`). Without it those two calls fail with a clear "No credentials" error; the read-only tools (`reasoner_gate`, `reasoner_estimate`, `reasoner_presets`, `reasoner_health`) work regardless, matching their unauthenticated HTTP counterparts.

### Streamable HTTP (hosted deployments)

For a deployment that wants an MCP endpoint without a second process, set:

```bash
ENABLE_MCP_HTTP=true
```

This mounts the MCP server at `/mcp` on the same FastAPI app that serves the REST API. Off by default — most installs use stdio instead. Authenticate the same way as the REST API: `Authorization: Bearer <key>` on the request.

---

## Tools

| Tool | Cost | Description |
| --- | --- | --- |
| `reasoner_run` | Paid | Run a reasoning pipeline; blocks and reports per-phase progress. |
| `reasoner_followup` | Paid | Continue a conversation with a prior synthesis as context. |
| `reasoner_gate` | Free | Preview routing (direct / web search / pipeline + method) without running it. |
| `reasoner_estimate` | Free | Estimate tokens, cost, and duration without running it. |
| `reasoner_presets` | Free | List available presets with method, description, and primary model. |
| `reasoner_health` | Free | Liveness and dependency status. |

There is no admin, key-management, or GDPR tool on this surface, and there will not be — that boundary is enforced by a test (`tests/test_mcp_tools.py`), not just a convention.

### Progress

`reasoner_run` and `reasoner_followup` emit an MCP progress notification per pipeline phase (`phase_start` / `phase_complete`), so a host UI can show "Phase 3: Critique" instead of sitting on an opaque 20–90 second call.

### Idempotency

Pass `client_run_id` to make a call retry-safe — reusing an id in flight returns a clean tool error instead of running (and billing) the pipeline twice. Same contract as the REST API's `client_run_id`.

---

## What this does not do

- **No per-session concurrency limit.** An agent that fires several `reasoner_run` calls back-to-back can run them concurrently, each billed independently. Standard function-calling agent loops call one tool, wait for the result, then decide the next action, so this has not been a problem in practice — but it is not enforced, only assumed. If you are wiring an agent loop that can call tools without waiting, add your own throttling in front of it.
- **No structured-output schema pinning.** Tool results are returned as an MCP structured-content dict, auto-derived from the Python return type. The shape matches `RunResult`/`RunSummary` (`synthesis`, `critical_insights`, `claim_labels`, `action_blueprint`, `citations`, `total_cost_usd`, ...) but is not (yet) published as a versioned JSON Schema the way `sdk/contract/tools.json` pins the HTTP tool-discovery format.

## See also

- [`/docs/mcp`](https://reasoner.app/docs/mcp) — this document, published for users of the hosted app. Keep the two in step: setup, tool list, and the caveats below are the same contract.
- [`/docs/agent-integration`](https://reasoner.app/docs/agent-integration) — the general agent integration guide (HTTP surface, retry semantics, what to do with labelled claims). Most of it applies here too; the MCP-specific parts are this document.
- `tests/test_mcp_tools.py` — the contract this document describes, enforced.
