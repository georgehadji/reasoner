# Context: Sandbox Worker

## Directory: `src/reasoner/infrastructure/execution/sandbox_worker`

## Description
Sandbox environment workers for isolated, secure execution of generated code.

## Files
- **`Dockerfile`**: Code or resource asset facilitating system functionality.
- **`__init__.py`**: Sandbox worker — the only process with Docker access.
- **`__main__.py`**: Entrypoint: ``python -m reasoner.infrastructure.execution.sandbox_worker``.
- **`app.py`**: Sandbox worker HTTP API — the only surface `backend` talks to for code
- **`docker_runner.py`**: Non-root UID/GID baked into the sandbox image (sandbox_image/Dockerfile)

## Subfolders
- **`sandbox_image`**: Docker configurations and build specifications for the containerized execution sandbox.
