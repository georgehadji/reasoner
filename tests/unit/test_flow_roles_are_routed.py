"""Every role a flow calls is routed by every preset that runs that flow (FLOW-2).

docs/plans/audit-remediation-2-2026-10-20.md FLOW-2: the jury roles and the
dialectical and socratic perspective roles were routed by no preset, so they
all ran on the preset's primary model, and validate_presets passed because it
checked fewer roles than the flows use. This test makes the two lists one fact:
it reads the roles from the flow code itself (AST) and checks each preset.

A role reaches ``call_llm`` either as a string literal (``role="scoring"``) or
through a variable (jury generators, Delphi experts, perspectives). The second
kind cannot be read from the AST, so each flow that uses it declares its roles
in DYNAMIC_ROLES below, and a test fails if a flow passes a variable role
without an entry there.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path

import pytest

import reasoner.application.flows as flows_pkg
from reasoner.application.flows.factory import WorkflowFactory
from reasoner.application.flows.jury_phases import (
    JURY_CRITIC_ROLES,
    JURY_GENERATOR_ROLES,
    JURY_PANEL_CRITIC_ROLE,
)
from reasoner.core.perspectives import DEFAULT_PERSPECTIVES
from reasoner.domain.pipeline_state import PipelineState
from reasoner.domain.preset_core import _KNOWN_ROUTING_ROLES
from reasoner.domain.preset_registry import PRESETS

FLOWS_DIR = Path(flows_pkg.__file__).parent

# Roles a preset may leave on its primary model on purpose: the method's own
# main step, which is the job its primary model was chosen for.
PRIMARY_OK_ROLES = frozenset({
    "primary",
    "cove_draft",
    "tot_generate",
    "writing_draft",
    "coding_generate",
    "brainstorm_generate",
    # SoT and PoT run every step on one model by design: the skeleton, the
    # parallel solves and the assembly share one voice.
    "sot_skeleton", "sot_solve", "sot_assemble",
    "pot_generate", "pot_execute", "pot_interpret",
})

_PERSPECTIVE_ROLES = tuple(p.name for p in DEFAULT_PERSPECTIVES)

# Roles passed to call_llm through a variable, per flow method.
DYNAMIC_ROLES: dict[str, tuple[str, ...]] = {
    "jury": (*JURY_GENERATOR_ROLES, *JURY_CRITIC_ROLES, JURY_PANEL_CRITIC_ROLE),
    "delphi": ("expert_1", "expert_2", "expert_3", "expert_4"),
    "multi_perspective": _PERSPECTIVE_ROLES,
    "cross_language": _PERSPECTIVE_ROLES,
    "subagent": _PERSPECTIVE_ROLES,
}

# image-gen presets are served by api/routes/images.py, which calls the image
# model directly; they never run the text flow the factory maps them to.
NOT_TEXT_FLOWS = frozenset({"image_gen"})


def _role_args(tree: ast.AST) -> tuple[set[str], bool]:
    """Literal ``role=`` values in *tree*, and whether any ``role=`` is not a literal."""
    literals: set[str] = set()
    dynamic = False
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "role":
            # `"a" if side == "A" else "b"` names both of its roles.
            values = (
                [node.value.body, node.value.orelse]
                if isinstance(node.value, ast.IfExp) else [node.value]
            )
            for value in values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    literals.add(value.value)
                else:
                    dynamic = True
    return literals, dynamic


def _phase_roles(method: str) -> tuple[set[str], bool]:
    steps = WorkflowFactory().get_strategy(method).get_phases(PipelineState(problem="x"))
    roles: set[str] = set()
    dynamic = False
    for step in steps:
        tree = ast.parse(textwrap.dedent(inspect.getsource(step.fn)))
        found, is_dynamic = _role_args(tree)
        roles |= found
        dynamic = dynamic or is_dynamic
    return roles, dynamic


def _norm(method: str) -> str:
    return method.replace("-", "_")


def test_every_literal_role_in_the_flows_is_a_known_routing_role():
    unknown: dict[str, set[str]] = {}
    for path in sorted(FLOWS_DIR.rglob("*.py")):
        literals, _ = _role_args(ast.parse(path.read_text(encoding="utf-8")))
        if missing := literals - _KNOWN_ROUTING_ROLES:
            unknown[path.name] = missing
    assert not unknown, f"roles a preset cannot route: {unknown}"


def test_every_dynamic_role_is_a_known_routing_role():
    declared = {role for roles in DYNAMIC_ROLES.values() for role in roles}
    assert declared <= _KNOWN_ROUTING_ROLES, sorted(declared - _KNOWN_ROUTING_ROLES)


@pytest.mark.parametrize("method", sorted({_norm(p["method"]) for p in PRESETS.values()}))
def test_a_flow_with_variable_roles_declares_them(method):
    if method in NOT_TEXT_FLOWS:
        return
    _, dynamic = _phase_roles(method)
    assert not dynamic or method in DYNAMIC_ROLES, (
        f"{method} passes a variable role to call_llm; list its roles in DYNAMIC_ROLES"
    )


@pytest.mark.parametrize("name", sorted(PRESETS))
def test_preset_routes_every_role_its_flow_uses(name):
    preset = PRESETS[name]
    method = _norm(preset["method"])
    if method in NOT_TEXT_FLOWS or "test" in name or "experimental" in name:
        return
    used, _ = _phase_roles(method)
    used |= set(DYNAMIC_ROLES.get(method, ()))
    unrouted = used - PRIMARY_OK_ROLES - set(preset["routing"])
    assert not unrouted, f"{name} runs {sorted(unrouted)} on its primary model"


def test_validate_presets_passes(capsys):
    """The bloc and one-model-per-role rules hold for the routes added above.

    scripts/validate_presets.py is not run by any workflow, so its checks on
    the new role groups would otherwise go unenforced.
    """
    import importlib.util

    script = Path(__file__).resolve().parents[2] / "scripts" / "validate_presets.py"
    spec = importlib.util.spec_from_file_location("validate_presets", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main() == 0, capsys.readouterr().out


def test_jury_critics_see_each_candidates_solution_and_claims():
    """Critics scored factuality from a one-line approach summary (FLOW-2)."""
    from reasoner.core.constants_limits import TRUNCATION
    from reasoner.domain.core_types import GenerationCandidate
    from reasoner.phases.jury import jury_critic_prompt

    state = PipelineState(problem="x")
    state.generation_candidates = [GenerationCandidate(
        generator_id="generator_1", model_used="m", solution="S" * (TRUNCATION.CONTENT + 500),
        confidence=0.5, key_claims=["water boils at 100C at sea level"], approach_summary="a",
    )]
    prompt = jury_critic_prompt(state)
    assert "S" * TRUNCATION.CONTENT in prompt
    assert "S" * (TRUNCATION.CONTENT + 1) not in prompt
    assert "water boils at 100C at sea level" in prompt
