"""
Self-Healing Loop Orchestrator

This script connects the independent self-healing scripts into a single
pipeline:
1. Static Loop: Introspection -> Test Generation
2. Runtime Loop: Smoke Testing (deployment verification)
3. Evolutionary Loop: Report Generation

Usage:
    python src/reasoner/healing/run_healing.py
"""

import logging
import sys
import subprocess
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("healing-orchestrator")

HEALING_DIR = Path(__file__).parent
PROJECT_ROOT = HEALING_DIR.parent.parent.parent

def run_script(script_path: Path, description: str) -> bool:
    """Run a python script and return success."""
    logger.info(f"Running {description}: {script_path.name}")
    try:
        # Use sys.executable to ensure we use the same environment
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            logger.info(f"β… {description} SUCCEEDED")
            if result.stdout:
                print(result.stdout)
            return True
        else:
            logger.error(f"β ERROR: {description} FAILED with code {result.returncode}")
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            return False
    except Exception as e:
        logger.error(f"β CRITICAL: Failed to execute {description}: {e}")
        return False

def main():
    logger.info("="*80)
    logger.info("STARTING REASONER SELF-HEALING PIPELINE")
    logger.info("="*80)

    # ── E5: Export runtime telemetry context (non-fatal) ──
    try:
        from reasoner.healing.telemetry_exporter import export_healing_context
        if export_healing_context():
            logger.info("Telemetry context exported — healing has runtime data")
    except Exception as exc:
        logger.debug("Telemetry context export skipped: %s", exc)

    # 1. LOOP 1: Static Healing
    # Phase 1.1: Introspection
    if not run_script(HEALING_DIR / "introspection_engine.py", "Loop 1.1: Codebase Introspection"):
        logger.error("Healing pipeline aborted at Loop 1.1")
        sys.exit(1)

    # Phase 1.2: Test Generation
    if not run_script(HEALING_DIR / "test_generation_engine.py", "Loop 1.2: Autonomous Test Generation"):
        logger.warning("Loop 1.2 failed, but continuing pipeline...")

    # 2. LOOP 2: Runtime Healing (Smoke Tests)
    # Check if smoke tests exist
    smoke_test_dir = HEALING_DIR / "smoke_tests"
    if smoke_test_dir.exists():
        logger.info("Running Loop 2: Runtime Smoke Tests")
        try:
            import pytest
            ret = pytest.main([str(smoke_test_dir), "-v"])
            if ret == 0:
                logger.info("β… Loop 2: Smoke Tests PASSED")
            else:
                logger.warning(f"β Loop 2: Smoke Tests FAILED with code {ret}")
        except ImportError:
            logger.error("pytest not found; skipping smoke tests")
    else:
        logger.info("Loop 2: Smoke tests directory not found, skipping.")

    logger.info("="*80)
    logger.info("SELF-HEALING PIPELINE COMPLETE")
    logger.info("="*80)

if __name__ == "__main__":
    main()
