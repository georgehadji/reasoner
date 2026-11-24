"""WS10-4 / WS8-2 / WS12-7: every third-party import must be declared.

The production image installs `requirements.txt` only. Six names the code imports
(sentry_sdk, prometheus_client, numpy, yaml, rich, click) were reachable only as
transitive pins or not at all, so the image shipped without Sentry or metrics and
the metrics endpoint answered with an empty body.
"""

import ast
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "reasoner"

# import name -> distribution name, where they differ
_DIST = {
    "docx": "python-docx",
    "dotenv": "python-dotenv",
    "google": "google-genai",
    "jwt": "pyjwt",
    "magic": "python-magic",
    "sentry_sdk": "sentry-sdk",
    "prometheus_client": "prometheus-client",
    "yaml": "pyyaml",
}

# Imported behind a guard, declared elsewhere on purpose.
#   langfuse: no release matches the imports (audit 8 D6); deleted in Phase 10.
_GUARDED = {"langfuse"}


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _declared() -> set[str]:
    names: set[str] = set()
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        m = re.match(r"([A-Za-z0-9_.\-]+)", line)
        if m and not line.startswith("-"):
            names.add(_norm(m.group(1)))
    extras = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "optional-dependencies"
    ]
    for reqs in extras.values():
        for req in reqs:
            names.add(_norm(re.match(r"([A-Za-z0-9_.\-]+)", req).group(1)))
    return names


def _imported() -> dict[str, str]:
    found: dict[str, str] = {}
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                tops = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                tops = [node.module.split(".")[0]]
            else:
                continue
            for top in tops:
                if top not in sys.stdlib_module_names and top != "reasoner":
                    found.setdefault(top, str(path.relative_to(ROOT)))
    return found


def test_every_third_party_import_is_declared():
    declared = _declared()
    missing = {
        top: where
        for top, where in _imported().items()
        if top not in _GUARDED and _norm(_DIST.get(top, top)) not in declared
    }
    assert not missing, f"imported under src/reasoner but not declared: {missing}"


def test_production_refuses_to_boot_without_prometheus():
    import pytest

    from reasoner.api.metrics import require_metrics_backend

    with pytest.raises(RuntimeError, match="prometheus_client"):
        require_metrics_backend("production", available=False)
    require_metrics_backend("production", available=True)
    require_metrics_backend("development", available=False)


def test_production_refuses_to_boot_with_dsn_but_no_sentry_sdk(monkeypatch):
    import pytest

    from reasoner.api import sentry

    monkeypatch.setattr(sentry, "_HAS_SENTRY", False)
    monkeypatch.setattr(sentry.settings, "SENTRY_DSN", "https://k@o0.ingest.sentry.io/1")
    monkeypatch.setattr(sentry.settings, "ENVIRONMENT", "production")
    with pytest.raises(RuntimeError, match="sentry-sdk"):
        sentry.init_sentry()

    monkeypatch.setattr(sentry.settings, "ENVIRONMENT", "development")
    sentry.init_sentry()  # warns, does not raise
