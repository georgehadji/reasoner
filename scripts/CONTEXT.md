# Context: Scripts

## Directory: `scripts`

## Description
Utility automation scripts for running servers, executing specialized tests, verifying environments, or packaging builds.

## Files
- **`capture_article_baseline.py`**: Capture and update the Article pipeline baseline.
- **`check_no_registry_bypass.py`**: CI guard: application/domain/core must not directly import infrastructure.llm.registry.
- **`check_skill_maps.py`**: Detect drift between .claude/skills/map-*/SKILL.md and the folders they map.
- **`ci-local.sh`**: Code or resource asset facilitating system functionality.
- **`cleanup_streaming.py`**: Remove _stream_direct_answer
- **`count_importlinter_exceptions.py`**: Semantic counter for `.importlinter`'s `ignore_imports` exception list.
- **`extract_e1.py`**: direct.py
- **`extract_run_stream.py`**: Extract the full body of run_stream
- **`fix_importlinter.py`**: Example line: - reasoner.core.search -> reasoner.infrastructure.llm.registry (l.44)
- **`jury_fix_test.py`**: Quick jury fix verification.
- **`lock_requirements.sh`**: Code or resource asset facilitating system functionality.
- **`migrate_encryption_v2.py`**: Look for events where payload is NOT a JSON object with a '_e' key, or _blind_index is missing
- **`migrate_events_sqlite_to_pg.py`**: Note: For a robust migration we ideally bypass the DomainEvent abstractions
- **`move_methods.py`**: Find the start of to_dict
- **`mypy_ratchet.py`**: Ratchet for `mypy src/reasoner` violation count.
- **`package_coverage_gate.py`**: Per-package coverage floor, read from an existing coverage.xml.
- **`pin_base_images.sh`**: Code or resource asset facilitating system functionality.
- **`re_extract_e1.py`**: The new run_stream implementation
- **`ruff_ratchet.py`**: Ratchet for `ruff check src/` violation count.
- **`run_3more_tests.py`**: Run 3 additional method API tests sequentially.
- **`run_batch4.py`**: Code or resource asset facilitating system functionality.
- **`run_method_tests.py`**: Run 4 method API tests sequentially.
- **`scan-secrets.py`**: Secret scanner — detect API keys and tokens in source code.
- **`start_all.py`**: Start all Reasoner servers.
- **`update_mindmap_meta.py`**: ── Live counts ──────────────────────────────────────────────────────────────
- **`update_openrouter_catalogue.py`**: Refresh the bundled OpenRouter model catalogue.
- **`validate_presets.py`**: Below this, a model that silently samples at its fixed 1.0 default is far
- **`verify_swaps.py`**: Verify model swaps fix the budget preset JSON format issues.

## Subfolders
*No subfolders in this directory.*
