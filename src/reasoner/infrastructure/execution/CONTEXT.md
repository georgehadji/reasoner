# Context: Execution

## Directory: `src/reasoner/infrastructure/execution`

## Description
Execution environments, containerized execution workers, and sandboxing infrastructure.

## Files
- **`__init__.py`**: Execution adapters package.
- **`container_sandbox.py`**: ContainerExecutionSandbox — the approved isolated CodeExecutorPort adapter.
- **`noop_executor.py`**: NoopExecutor — graceful degradation when sandbox is unavailable.
- **`subprocess_executor.py`**: 1. AST safety guard

## Subfolders
- **`runners`**: Specific execution runner strategies (local, container, remote).
- **`sandbox_worker`**: Sandbox environment workers for isolated, secure execution of generated code.
