"""Every hard production requirement must be documented in .env.example.

docker-compose.yml hardcodes ENVIRONMENT=production, so a variable that the app
raises on is a first-deploy crash for anyone following DEPLOY.md. These vars all
had production guards in code while appearing in neither file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Variables whose absence raises (rather than degrades) when ENVIRONMENT=production.
PRODUCTION_REQUIRED_VARS = [
    # core/settings.py — raises when CSRF_ENFORCE_BACKEND is on
    "CSRF_SECRET",
    # security/encryption.py — EncryptionService.__init__ raises in production
    "ENCRYPTION_KEY",
    "BLIND_INDEX_KEY",
    # api/__init__.py — admin endpoints are unusable without it
    "ADMIN_API_KEY",
    # infrastructure/auth/__init__.py — LocalAuthAdapter (HS256) is refused in
    # production, so Supabase is mandatory rather than "optional but recommended"
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
]

# Not required to boot, but a deploy that omits them silently loses a headline
# feature, so they must at least be discoverable.
OPERATIONALLY_REQUIRED_VARS = [
    "METRICS_ALLOWED_IPS",  # observability overlay cannot scrape /api/metrics
    "BRAVE_SEARCH_API_KEY",  # web-grounded presets degrade to no search
    "SENTRY_DSN",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
]


def _documented_keys(path: Path) -> set[str]:
    """Env keys declared in a dotenv-style file, including commented-out ones."""
    keys: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip().lstrip("#").strip()
        name, sep, _ = line.partition("=")
        if sep and name and name.replace("_", "").isalnum() and name.isupper():
            keys.add(name)
    return keys


@pytest.fixture(scope="module")
def env_example_keys() -> set[str]:
    return _documented_keys(REPO_ROOT / ".env.example")


@pytest.mark.parametrize("var", PRODUCTION_REQUIRED_VARS)
def test_production_required_var_is_in_env_example(var, env_example_keys):
    assert var in env_example_keys, (
        f"{var} raises in production but is missing from .env.example — "
        "following DEPLOY.md would crash the backend on first deploy"
    )


@pytest.mark.parametrize("var", OPERATIONALLY_REQUIRED_VARS)
def test_operationally_required_var_is_in_env_example(var, env_example_keys):
    assert var in env_example_keys, f"{var} is undiscoverable without .env.example"


@pytest.mark.parametrize("var", ["ENCRYPTION_KEY", "BLIND_INDEX_KEY"])
def test_secret_generation_is_documented_in_deploy_guide(var):
    """A key in the required list is useless without the command that makes one."""
    deploy_md = (REPO_ROOT / "DEPLOY.md").read_text(encoding="utf-8")
    assert var in deploy_md, f"{var} is required in production but absent from DEPLOY.md"


def _preflight():
    """Load scripts/preflight_check.py, which is outside the importable package."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "preflight_check", REPO_ROOT / "scripts" / "preflight_check.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_preflight_blocks_the_unedited_template():
    """`cp .env.example .env` then deploying must fail loudly, not at runtime."""
    preflight = _preflight()
    env = preflight.parse_env_file(REPO_ROOT / ".env.example")
    errors, _ = preflight.check(env)

    blocked = " ".join(errors)
    for var in ("CSRF_SECRET", "ENCRYPTION_KEY", "BLIND_INDEX_KEY", "SUPABASE_URL"):
        assert var in blocked, f"preflight let the {var} placeholder through"


def test_preflight_rejects_malformed_fernet_keys():
    preflight = _preflight()

    assert not preflight.is_fernet_key("not-base64-at-all")
    assert not preflight.is_fernet_key("c2hvcnQ=")  # valid base64, wrong length

    from cryptography.fernet import Fernet

    assert preflight.is_fernet_key(Fernet.generate_key().decode())


def test_preflight_covers_every_blocking_production_var():
    """The guard list and the script must not drift apart."""
    preflight = _preflight()
    checked = {name for name, _ in preflight.BLOCKING}

    for var in PRODUCTION_REQUIRED_VARS:
        assert var in checked, f"preflight_check.py does not validate {var}"


def test_env_example_ships_no_real_secrets(env_example_keys):
    """The template must stay a template."""
    for raw in (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        if name.strip() in {"ENCRYPTION_KEY", "BLIND_INDEX_KEY", "CSRF_SECRET", "ADMIN_API_KEY"}:
            assert not value.strip(), f"{name} must be left blank in .env.example"
