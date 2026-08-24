# Context: Runners

## Directory: `src/reasoner/infrastructure/execution/runners`

## Description
Specific execution runner strategies (local, container, remote).

## Files
- **`__init__.py`**: Language-runner strategy registry for the container sandbox.
- **`base.py`**: Strategy interface for building per-language container invocations.
- **`python_runner.py`**: Python language runner — the only concrete LanguageRunner today.

## Subfolders
*No subfolders in this directory.*
