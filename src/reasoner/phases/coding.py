"""Coding pipeline prompts — production-grade code generation."""

from __future__ import annotations

from reasoner.phases._shared import (
    JSON_ONLY_FOOTER,
    TRUNCATION,
    PipelineState,
    _wrap_user_input,
)

__all__ = [
    "CODING_SPEC_SYSTEM",
    "CODING_GENERATE_SYSTEM",
    "CODING_REVIEW_SYSTEM",
    "CODING_TESTS_SYSTEM",
    "CODING_ASSEMBLE_SYSTEM",
    "coding_spec_prompt",
    "coding_generate_prompt",
    "coding_review_prompt",
    "coding_tests_prompt",
    "coding_assemble_prompt",
]

# ── Verbalized sampling helpers ──────────────────────────────────────────────

def _with_reasoning(system_prompt: str, focus: str) -> str:
    """Prefix a system prompt with verbalized-sampling instruction.

    When CODING_VERBALIZED_SAMPLING is enabled, models are instructed to
    reason inside <think> tags before producing their output. The parser
    already strips these tags; they are invisible to downstream consumers.
    """
    return (
        f"<think>\n"
        f"Before producing your output, reason step-by-step about: {focus}.\n"
        f"Consider edge cases, error handling, security boundaries, and testability.\n"
        f"Be concise — no more than 5-10 sentences of reasoning.\n"
        f"</think>\n\n"
        f"{system_prompt}"
    )


def strip_reasoning_from_code(raw_code: str) -> str:
    """Strip <think> blocks from generated code before writing to file."""
    import re
    return re.sub(r"<think>[\s\S]*?</think>", "", raw_code).strip()


# ── Quality contract appended to every generation prompt ──────────────────────
_CODE_QUALITY_CONTRACT = (
    "\n\nPRODUCTION CODE CONTRACT — every file you write MUST satisfy ALL of these:\n"
    "1. Full type annotations on every function signature (parameters + return type).\n"
    "2. Specific exception types — never bare `except Exception` or silent swallows.\n"
    "3. Input validation at every public API boundary (raise on invalid input).\n"
    "4. No hardcoded secrets, credentials, tokens, or magic numbers.\n"
    "5. Structured logging with contextual fields — zero print() statements.\n"
    "6. Complete implementation — no TODO stubs, no `pass`, no placeholder comments.\n"
    "7. Thread/async safety wherever concurrency is implied by the interface.\n"
    "8. Comments only when the WHY is non-obvious — never restate what the code does."
)

# ── Phase 2: Spec Analysis ─────────────────────────────────────────────────────
CODING_SPEC_SYSTEM = (
    "You are an elite software architect specializing in production-grade systems. "
    "Analyze the coding request and produce a precise technical specification. "
    "Identify: what language/framework is implied, the minimal set of files/modules needed, "
    "public interfaces and data contracts between them, external dependencies, "
    "error handling strategy, security boundaries, and testability requirements. "
    "Do NOT add features the user did not request. Do NOT over-engineer. "
    "Prefer the simplest correct architecture. "
    + JSON_ONLY_FOOTER
)


def coding_spec_prompt(state: PipelineState) -> str:
    # BUG-FIX: TRUNCATION is a TruncationLimits object, not a dict. Use dot notation.
    problem = _wrap_user_input(state.problem[:TRUNCATION.PROBLEM])
    return (
        f"Coding request:\n{problem}\n\n"
        "Produce a technical specification as JSON:\n"
        "{\n"
        '  "language": "<primary programming language>",\n'
        '  "framework": "<framework or null>",\n'
        '  "architecture_summary": "<1-2 sentence description of the solution architecture>",\n'
        '  "files": [\n'
        '    {\n'
        '      "path": "<relative file path>",\n'
        '      "purpose": "<what this file does>",\n'
        '      "public_interface": ["<function/class/constant exported>", ...],\n'
        '      "dependencies": ["<other file paths or external packages it imports>", ...]\n'
        "    }\n"
        "  ],\n"
        '  "error_strategy": "<how errors propagate across the system>",\n'
        '  "security_notes": ["<any security boundary or concern>", ...],\n'
        '  "test_strategy": "<brief description of what to test>"\n'
        "}"
    )


# ── Phase 3: Code Generation ───────────────────────────────────────────────────
CODING_GENERATE_SYSTEM = (
    "You are a senior software engineer writing production-grade code for a specific file. "
    "You will receive a technical specification and must implement exactly one file. "
    "Output the complete, runnable file content. "
    "Do not truncate or abbreviate — every function must be fully implemented."
    + _CODE_QUALITY_CONTRACT
    + "\n\n"
    + JSON_ONLY_FOOTER
)


def coding_generate_prompt(state: PipelineState, file_spec: dict) -> str:
    # BUG-FIX: TRUNCATION is a TruncationLimits object, not a dict. Use dot notation.
    problem = _wrap_user_input(state.problem[:TRUNCATION.PROBLEM])
    spec = state.coding_state.get("spec", {})
    arch = spec.get("architecture_summary", "")
    lang = spec.get("language", "")
    framework = spec.get("framework", "")

    stack_line = f"Language: {lang}"
    if framework:
        stack_line += f" | Framework: {framework}"

    deps = ", ".join(file_spec.get("dependencies", [])) or "none"
    interface = ", ".join(file_spec.get("public_interface", [])) or "as needed"

    return (
        f"Original request:\n{problem}\n\n"
        f"Architecture: {arch}\n"
        f"{stack_line}\n\n"
        f"File to implement: {file_spec['path']}\n"
        f"Purpose: {file_spec['purpose']}\n"
        f"Public interface to expose: {interface}\n"
        f"Imports/dependencies: {deps}\n"
        f"Error strategy: {spec.get('error_strategy', 'raise specific exceptions')}\n\n"
        "Return JSON:\n"
        "{\n"
        '  "path": "<file path>",\n'
        '  "content": "<complete file source code as a single string with \\n for newlines>",\n'
        '  "language": "<language>",\n'
        '  "key_decisions": ["<non-obvious implementation decision>", ...]\n'
        "}"
    )


# ── Phase 3.5: Adversarial Security & Quality Review ──────────────────────────
CODING_REVIEW_SYSTEM = (
    "You are a principal security engineer and code quality adversary. "
    "You review generated code with maximum hostility — your job is to find every flaw "
    "before it reaches production. "
    "Check for: security vulnerabilities (injection, SSRF, path traversal, hardcoded secrets, "
    "broken auth), silent error swallows, missing input validation, race conditions, "
    "missing type annotations, incomplete implementations, dead code, "
    "and architectural inconsistencies across files. "
    "Be specific: cite file path and the exact issue. "
    + JSON_ONLY_FOOTER
)


def coding_review_prompt(state: PipelineState) -> str:
    spec = state.coding_state.get("spec", {})
    files = state.coding_state.get("generated_files", [])

    files_summary = ""
    for f in files:
        path = f.get("path", "unknown")
        content_preview = f.get("content", "")[:800]
        decisions = "; ".join(f.get("key_decisions", []))
        files_summary += (
            f"\n--- {path} ---\n"
            f"{content_preview}\n"
            f"[Key decisions: {decisions or 'none stated'}]\n"
        )

    return (
        f"Architecture: {spec.get('architecture_summary', 'N/A')}\n"
        f"Error strategy: {spec.get('error_strategy', 'N/A')}\n\n"
        f"Generated files (content preview):{files_summary}\n\n"
        "Return JSON with your adversarial findings:\n"
        "{\n"
        '  "critical_issues": [\n'
        '    {"file": "<path>", "issue": "<description>", "fix": "<concrete fix>"}\n'
        "  ],\n"
        '  "high_issues": [\n'
        '    {"file": "<path>", "issue": "<description>", "fix": "<concrete fix>"}\n'
        "  ],\n"
        '  "medium_issues": [\n'
        '    {"file": "<path>", "issue": "<description>"}\n'
        "  ],\n"
        '  "overall_verdict": "<APPROVED | NEEDS_FIXES>",\n'
        '  "security_posture": "<brief assessment>"\n'
        "}"
    )


# ── Phase 4: Test Generation ───────────────────────────────────────────────────
CODING_TESTS_SYSTEM = (
    "You are a TDD specialist writing comprehensive tests for production code. "
    "Write tests that catch real bugs — not happy-path theatre. "
    "Cover: normal cases, boundary values, invalid inputs, error paths, "
    "and any security issues flagged in the review. "
    "Use the project's implied test framework (pytest for Python, jest for JS/TS, etc.). "
    "Tests must be runnable without modification."
    + _CODE_QUALITY_CONTRACT
    + "\n\n"
    + JSON_ONLY_FOOTER
)


def coding_tests_prompt(state: PipelineState) -> str:
    spec = state.coding_state.get("spec", {})
    files = state.coding_state.get("generated_files", [])
    review = state.coding_state.get("review", {})

    critical = review.get("critical_issues", [])
    high = review.get("high_issues", [])
    issues_text = ""
    if critical or high:
        issues_text = "\nKnown issues to regression-test:\n"
        for issue in critical + high:
            issues_text += f"  - [{issue.get('file', '?')}] {issue.get('issue', '')}\n"

    files_list = "\n".join(f"  - {f['path']}: {f.get('purpose', '')}" for f in files)
    test_strategy = spec.get("test_strategy", "unit + integration tests")

    return (
        f"Test strategy: {test_strategy}\n"
        f"Language: {spec.get('language', 'unknown')}\n\n"
        f"Files to test:\n{files_list}\n"
        f"{issues_text}\n"
        "Return JSON:\n"
        "{\n"
        '  "test_files": [\n'
        '    {\n'
        '      "path": "<test file path>",\n'
        '      "content": "<complete test file source as string with \\n for newlines>",\n'
        '      "covers": ["<what behavior is tested>", ...]\n'
        "    }\n"
        "  ],\n"
        '  "coverage_estimate": "<X% of critical paths>",\n'
        '  "missing_coverage": ["<gap>", ...]\n'
        "}"
    )


# ── Phase 5: Final Assembly ────────────────────────────────────────────────────
CODING_ASSEMBLE_SYSTEM = (
    "You are a principal engineer doing the final integration pass. "
    "You have the generated files, the adversarial review, and the tests. "
    "Your job: apply the critical and high fixes from the review, "
    "ensure all files are mutually consistent (imports match exports, "
    "types are compatible across module boundaries), "
    "and produce the definitive production-ready version of each file. "
    "Do not re-generate files that had no issues — return them verbatim. "
    "Output a structured delivery with a clear README section."
    + _CODE_QUALITY_CONTRACT
    + "\n\n"
    + JSON_ONLY_FOOTER
)


def coding_assemble_prompt(state: PipelineState) -> str:
    spec = state.coding_state.get("spec", {})
    files = state.coding_state.get("generated_files", [])
    review = state.coding_state.get("review", {})
    tests = state.coding_state.get("tests", {})

    critical = review.get("critical_issues", [])
    high = review.get("high_issues", [])
    verdict = review.get("overall_verdict", "APPROVED")
    security_posture = review.get("security_posture", "")

    fixes_needed = ""
    if critical or high:
        fixes_needed = "\nFixes required (apply these):\n"
        for issue in critical:
            fixes_needed += f"  CRITICAL [{issue.get('file','?')}]: {issue.get('fix', issue.get('issue',''))}\n"
        for issue in high:
            fixes_needed += f"  HIGH [{issue.get('file','?')}]: {issue.get('fix', issue.get('issue',''))}\n"

    files_json = "\n".join(
        f"  {f['path']}: {len(f.get('content',''))} chars" for f in files
    )
    test_files_list = "\n".join(
        f"  {tf['path']}" for tf in tests.get("test_files", [])
    )

    return (
        f"Architecture: {spec.get('architecture_summary', 'N/A')}\n"
        f"Review verdict: {verdict} | Security: {security_posture}\n"
        f"{fixes_needed}\n"
        f"Generated files:\n{files_json}\n"
        f"Test files:\n{test_files_list or '  (none)'}\n\n"
        "Return JSON:\n"
        "{\n"
        '  "files": [\n'
        '    {\n'
        '      "path": "<file path>",\n'
        '      "content": "<final file source>",\n'
        '      "changed": <true if fixes were applied, false if unchanged>\n'
        "    }\n"
        "  ],\n"
        '  "readme": "<markdown string: setup instructions, file map, usage examples>",\n'
        '  "fixes_applied": ["<description of each fix applied>", ...],\n'
        '  "known_limitations": ["<any remaining caveat>", ...]\n'
        "}"
    )


# ── Conditional verbalized-sampling wrapping ──────────────────────────
# When CODING_VERBALIZED_SAMPLING is enabled, all system prompts are
# prefixed with a <think> instruction. The parser already strips these
# tags; downstream consumers see clean output.
from reasoner.core.settings import settings as _settings

if _settings.CODING_VERBALIZED_SAMPLING:
    CODING_SPEC_SYSTEM = _with_reasoning(
        CODING_SPEC_SYSTEM,
        focus="architecture, file boundaries, dependencies, error strategy",
    )
    CODING_GENERATE_SYSTEM = _with_reasoning(
        CODING_GENERATE_SYSTEM,
        focus="edge cases, type contracts, input validation, error propagation, async safety",
    )
    CODING_REVIEW_SYSTEM = _with_reasoning(
        CODING_REVIEW_SYSTEM,
        focus="security audit, code quality gaps, anti-patterns, test coverage",
    )
    CODING_TESTS_SYSTEM = _with_reasoning(
        CODING_TESTS_SYSTEM,
        focus="coverage strategy, edge-case enumeration, mock boundaries, integration points",
    )
    CODING_ASSEMBLE_SYSTEM = _with_reasoning(
        CODING_ASSEMBLE_SYSTEM,
        focus="integration surface, deployment readiness, documentation completeness",
    )
