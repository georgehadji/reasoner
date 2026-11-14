# healing/

CI-only analysis scripts, not imported by the application.

- `introspection_engine.py`: maps the codebase and writes `healing/introspection_report.*`.
- `test_generation_engine.py`: generates tests into `healing/generated_tests/`.

Both run from `.github/workflows/self-healing-ci.yml` (nightly or manual). Their outputs are generated; do not commit them.
