"""There is exactly one OpenRouter catalogue that code may load.

The repo carried three copies of ``openrouter_models.json``:

  src/reasoner/domain/  420 entries, current -- the one pricing.py and
                        image_model_catalogue.py load, and the one
                        scripts/update_openrouter_catalogue.py writes
  repo root             346 entries, ~74 behind; lacked anthropic/claude-sonnet-5
  docs/                 346 entries, a *different* stale snapshot again

Per docs/openrouter-catalogue-2026-08.md the root copy began life as a local
scratch dump that was never meant to be authoritative -- the fix for an empty
PRICING_DB was to commit a real catalogue under domain/. The scratch file was
left behind, and ``extract_image_models.py`` opened it by a bare relative
filename, so which snapshot it read depended on the caller's cwd.

The cost was not hypothetical: auditing the model whitelist against the root
copy reported 124 of 216 aliases as serving "dead" models -- including
claude-sonnet, the primary of half the presets. Every one of those was a false
positive produced by reading the wrong file.

The root copy and its reader are now deleted. The docs/ copy is kept as a dated
archive (map-docs lists it under "check the date before trusting"), so the rule
enforced here is not "only one file exists" but "no code loads anything except
the domain copy".
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

_ROOT = Path(__file__).resolve().parents[2]
_CANONICAL = _ROOT / "src" / "reasoner" / "domain" / "openrouter_models.json"
_SCANNED_DIRS = ("src", "scripts")
_FILENAMES = ("openrouter_models.json", "openrouter_models_formatted.txt")


@pytest.mark.unit
def test_the_canonical_catalogue_exists():
    assert _CANONICAL.is_file(), f"the one catalogue code may load is missing: {_CANONICAL}"


@pytest.mark.unit
@pytest.mark.parametrize("name", _FILENAMES)
def test_no_catalogue_copy_at_the_repo_root(name):
    """The scratch dump must not come back: it is what produced 124 false hits."""
    stray = _ROOT / name
    assert not stray.exists(), (
        f"{name} is back at the repo root. It is a stale scratch copy, not a "
        f"source of truth -- auditing against it reports models as dead that "
        f"are live. Delete it; the catalogue lives at {_CANONICAL.relative_to(_ROOT)}."
    )


@pytest.mark.unit
def test_no_module_opens_a_catalogue_by_bare_relative_path():
    """A bare filename resolves against cwd, so it reads whatever copy is nearest.

    That is exactly how the deleted extract_image_models.py picked up the stale
    root snapshot instead of the real catalogue: ``open('openrouter_models.json')``.

    Matched on the AST, not on text, so prose in docstrings, a multi-line
    ``Path(...) / "domain" / "openrouter_models.json"`` chain, and the filename
    appearing in scan-secrets.py's skip list are all correctly ignored -- only a
    literal filename handed straight to ``open()`` or ``Path()`` is a finding.
    """
    import ast

    offenders: list[str] = []
    for d in _SCANNED_DIRS:
        for py in (_ROOT / d).rglob("*.py"):
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except SyntaxError:  # pragma: no cover - not our concern here
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                fn = node.func
                name = fn.id if isinstance(fn, ast.Name) else (
                    fn.attr if isinstance(fn, ast.Attribute) else ""
                )
                if name not in ("open", "Path"):
                    continue
                first = node.args[0]
                if isinstance(first, ast.Constant) and first.value in _FILENAMES:
                    offenders.append(
                        f"{py.relative_to(_ROOT)}:{node.lineno}: "
                        f"{name}({first.value!r}) resolves against cwd"
                    )

    assert not offenders, (
        "catalogue opened by bare relative filename -- anchor it to "
        "src/reasoner/domain/ instead:\n  " + "\n  ".join(offenders)
    )


@pytest.mark.unit
def test_the_two_real_loaders_agree_on_the_path():
    """pricing.py and image_model_catalogue.py must read the same file."""
    from reasoner.infrastructure.llm import image_model_catalogue as imc

    pricing_path = Path(
        __import__("reasoner.domain.pricing", fromlist=["__file__"]).__file__
    ).with_name("openrouter_models.json")
    imc_path = Path(imc.__file__).resolve().parents[2] / "domain" / "openrouter_models.json"

    assert pricing_path.resolve() == _CANONICAL.resolve(), pricing_path
    assert imc_path.resolve() == _CANONICAL.resolve(), imc_path
