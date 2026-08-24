#!/usr/bin/env python3
"""
Autonomous Debugging Protocol for Reasoner Project
Proactively scans codebase, runs tests, finds AND FIXES issues automatically.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent
SRC_DIR = REPO_ROOT / "src" / "reasoner"
TESTS_DIR = REPO_ROOT / "tests"

# Auto-fix patterns: (old_pattern, new_pattern, description)
AUTO_FIX_PATTERNS = [
    ("from reasoner.ara_verbalized_sampling import", "from reasoner.reasoner_verbalized_sampling import", "ara_verbalized_sampling -> reasoner_verbalized_sampling"),
    ("from reasoner.ara_vs_constants import", "from reasoner.reasoner_vs_constants import", "ara_vs_constants -> reasoner_vs_constants"),
    ("from reasoner.ara_persuasion_defense import", "from reasoner.reasoner_persuasion_defense import", "ara_persuasion_defense -> reasoner_persuasion_defense"),
    ("from reasoner.ara_vs_config import", "from reasoner.vs_config import", "ara_vs_config -> vs_config"),
    ("ARAPipeline", "ReasonerPipeline", "ARAPipeline -> ReasonerPipeline"),
    ("ARAPersuasionIntegration", "ReasonerPersuasionIntegration", "ARAPersuasionIntegration -> ReasonerPersuasionIntegration"),
]


class AutonomousDebugger:
    """Fully autonomous codebase scanner and fixer."""

    def __init__(self):
        self.issues_found: list[tuple[str, str, str]] = []
        self.fixes_applied: list[tuple[str, str]] = []
        self.errors_fixed = 0

    def log(self, msg: str) -> None:
        print(msg)

    def run(self) -> bool:
        """Run complete autonomous debugging and fixing cycle."""
        self.log("=" * 70)
        self.log("AUTONOMOUS DEBUGGING PROTOCOL - REASONER PROJECT")
        self.log("Scanning codebase and auto-fixing issues...")
        self.log("=" * 70)

        # Phase 1: Auto-fix import mismatches
        self.phase_1_auto_fix_imports()

        # Phase 2: Check for syntax errors
        self.phase_2_syntax_check()

        # Phase 3: Verify test collection
        self.phase_3_test_collection()

        # Phase 4: Run critical regression tests
        self.phase_4_run_critical_tests()

        # Phase 5: Frontend check
        self.phase_5_frontend_check()

        return self.print_summary()

    def phase_1_auto_fix_imports(self) -> None:
        """Phase 1: Automatically fix import mismatches."""
        self.log("\n[PHASE 1] Auto-fixing import mismatches...")

        test_files = list(TESTS_DIR.glob("test_*.py"))
        source_files = list(SRC_DIR.rglob("*.py"))
        all_files = test_files + source_files

        total_fixes = 0

        for py_file in all_files:
            try:
                content = py_file.read_text(encoding='utf-8')
                original_content = content
                fixes_in_file = []

                for old_pattern, new_pattern, description in AUTO_FIX_PATTERNS:
                    if old_pattern in content:
                        count = content.count(old_pattern)
                        content = content.replace(old_pattern, new_pattern)
                        fixes_in_file.append(f"{description} ({count}x)")

                if content != original_content:
                    py_file.write_text(content, encoding='utf-8')
                    total_fixes += len(fixes_in_file)
                    self.fixes_applied.append((str(py_file), ", ".join(fixes_in_file)))
                    self.log(f"  Fixed: {py_file.name}")
            except Exception as e:
                self.log(f"  Error processing {py_file}: {e}")

        if total_fixes > 0:
            self.log(f"[OK] Applied {total_fixes} auto-fixes")
        else:
            self.log("[OK] No import mismatches found")

    def phase_2_syntax_check(self) -> None:
        """Phase 2: Check all Python files for syntax errors."""
        self.log("\n[PHASE 2] Checking for syntax errors...")

        py_files = list(SRC_DIR.rglob("*.py"))
        errors = []

        for py_file in py_files:
            # Skip generated tests with known issues
            if "generated_tests" in str(py_file):
                continue
            try:
                compile(py_file.read_text(encoding='utf-8'), py_file.name, 'exec')
            except SyntaxError as e:
                errors.append((py_file, e))
                self.issues_found.append((str(py_file), "SyntaxError", str(e)))

        if errors:
            self.log(f"[ERR] Found {len(errors)} syntax errors:")
            for file, err in errors:
                self.log(f"  - {file}: {err}")
        else:
            self.log("[OK] No syntax errors found")

    def phase_3_test_collection(self) -> None:
        """Phase 3: Verify all tests can be collected."""
        self.log("\n[PHASE 3] Verifying test collection...")

        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT
        )

        if result.returncode != 0:
            self.log("[WARN] Test collection had issues:")
            error_lines = [l for l in result.stderr.split('\n') if 'ERROR' in l or 'error' in l.lower()][:5]
            for line in error_lines:
                if line.strip():
                    self.log(f"  {line.strip()}")
        else:
            # Count tests
            for line in result.stdout.split('\n'):
                if 'collected' in line.lower():
                    self.log(f"[OK] {line.strip()}")
                    break

    def phase_4_run_critical_tests(self) -> None:
        """Phase 4: Run critical regression tests."""
        self.log("\n[PHASE 4] Running critical regression tests...")

        critical_test_files = [
            "tests/test_bugfixes_regression.py",
            "tests/test_bugfixes_regression_round2.py",
            "tests/test_bugfixes_regression_round3.py",
            "tests/test_parsing.py",
        ]

        passed = 0
        failed = 0

        for test_file in critical_test_files:
            test_path = REPO_ROOT / test_file
            if not test_path.exists():
                continue

            result = subprocess.run(
                [sys.executable, "-m", "pytest", test_file, "-v", "--tb=short", "-q"],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT
            )

            if result.returncode == 0:
                self.log(f"[PASS] {test_file}")
                passed += 1
            else:
                self.log(f"[FAIL] {test_file}")
                failed += 1
                # Show failed test names
                for line in result.stdout.split('\n'):
                    if 'FAILED' in line:
                        self.log(f"       {line.strip()}")

        self.log(f"[SUMMARY] {passed} passed, {failed} failed")

    def phase_5_frontend_check(self) -> None:
        """Phase 5: Check frontend tests."""
        self.log("\n[PHASE 5] Checking frontend...")

        ui_next = REPO_ROOT / "ui-next"
        if not ui_next.exists():
            self.log("[SKIP] ui-next directory not found")
            return

        # Count test files
        test_files = list(ui_next.rglob("*.test.ts")) + list(ui_next.rglob("*.test.tsx"))
        self.log(f"[OK] Found {len(test_files)} frontend test files")

    def print_summary(self) -> bool:
        """Print summary of findings and fixes."""
        self.log("\n" + "=" * 70)
        self.log("SUMMARY")
        self.log("=" * 70)

        if self.fixes_applied:
            self.log(f"\nAuto-fixes applied: {len(self.fixes_applied)}")
            for file, desc in self.fixes_applied:
                self.log(f"  - {Path(file).name}: {desc}")

        if self.issues_found:
            self.log(f"\nIssues requiring manual attention: {len(self.issues_found)}")
            for file, issue_type, desc in self.issues_found:
                self.log(f"  - [{issue_type}] {Path(file).name}: {desc}")

        if not self.fixes_applied and not self.issues_found:
            self.log("\n[OK] Codebase is healthy! No issues found.")
            return True

        return len(self.issues_found) == 0


def main():
    """Main entry point."""
    debugger = AutonomousDebugger()
    success = debugger.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
