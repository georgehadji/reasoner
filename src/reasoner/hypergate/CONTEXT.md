# Context: Hypergate

## Directory: `src/reasoner/hypergate`

## Description
Advanced multi-agent routing gateways and sub-orchestrators for managing parallel reasoning routes.

## Files
- **`__init__.py`**: Python package initialization module.
- **`base_sub_agent.py`**: ── Abstract interface ────────────────────────────────────────────
- **`gate_agent.py`**: Internal opaque taxonomy. The LLM sees only the letters (A-L), never the real method names.
- **`hyperagent.py`**: HyperGateAgent — orchestrates 5 focused sub-agents in parallel (Phase 1) and
- **`models.py`**: Data models for the HyperGate sub-agent communication protocol.

## Subfolders
- **`sub_agents`**: Hypergate sub-agent controllers coordinating specialized reasoning tasks.
