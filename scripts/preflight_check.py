#!/usr/bin/env python3
"""Validate a .env before deploying — run this instead of discovering gaps at runtime.

docker-compose.yml sets ENVIRONMENT=production, and several production guards
raise at import or on first store access. A missing variable therefore shows up
as a crash-looping container rather than a clear message, so check first:

    python scripts/preflight_check.py              # validate ./.env
    python scripts/preflight_check.py --env-file /path/to/.env
    python scripts/preflight_check.py --generate   # print fresh secrets

Exit code 0 means safe to deploy, 1 means at least one blocking problem.
"""

from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# (name, why it blocks) — absence of any of these raises in production.
BLOCKING: list[tuple[str, str]] = [
    ("CSRF_SECRET", "core/settings.py raises when CSRF_ENFORCE_BACKEND is on"),
    ("ENCRYPTION_KEY", "security/encryption.py raises; the Postgres and auth stores need it"),
    ("BLIND_INDEX_KEY", "security/encryption.py raises when building blind indexes"),
    ("ADMIN_API_KEY", "admin endpoints reject every request without it"),
    ("POSTGRES_PASSWORD", "docker-compose builds DATABASE_URL from it"),
    ("SUPABASE_URL", "LocalAuthAdapter (HS256) is refused in production"),
    ("SUPABASE_SERVICE_ROLE_KEY", "required to verify Supabase tokens server-side"),
]

# At least one of these must be present for any pipeline to run.
LLM_KEYS = [
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
]

# Absence degrades a feature silently rather than blocking startup.
WARNING: list[tuple[str, str]] = [
    ("BRAVE_SEARCH_API_KEY", "web-grounded and research presets run without search"),
    ("SENTRY_DSN", "no error tracking; /api/metrics still satisfies the observability gate"),
    ("METRICS_ALLOWED_IPS", "the observability overlay cannot scrape /api/metrics"),
    ("RESEND_API_KEY", "transactional email is logged instead of sent"),
    ("SPEND_CAP_MONTHLY_USD", "no monthly spend ceiling — set a cap at OpenRouter too"),
]


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, sep, value = line.partition("=")
        if sep:
            values[name.strip()] = value.strip().strip('"').strip("'")
    return values


def is_fernet_key(value: str) -> bool:
    """Fernet keys are 32 raw bytes, urlsafe-base64 encoded."""
    try:
        return len(base64.urlsafe_b64decode(value.encode())) == 32
    except Exception:
        return False


def generate_secrets() -> None:
    import secrets

    try:
        from cryptography.fernet import Fernet
    except ImportError:
        print("cryptography is not installed — run: pip install -r requirements.txt")
        raise SystemExit(1) from None

    print("# Paste these into your .env — regenerating them invalidates existing data.")
    print(f"ADMIN_API_KEY={secrets.token_urlsafe(32)}")
    print(f"CSRF_SECRET={secrets.token_urlsafe(32)}")
    print(f"ENCRYPTION_KEY={Fernet.generate_key().decode()}")
    print(f"BLIND_INDEX_KEY={Fernet.generate_key().decode()}")
    print(f"POSTGRES_PASSWORD={secrets.token_urlsafe(24)}")


def is_placeholder(value: str) -> bool:
    """Catch values copied straight from .env.example without editing."""
    lowered = value.lower()
    markers = ("your-", "your_", "<generate", "...", "sk-or-v1-...", "changeme", "xxx")
    return any(marker in lowered for marker in markers) or lowered.endswith("-here")


def check(env: dict[str, str]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    for name, reason in BLOCKING:
        value = env.get(name)
        if not value:
            errors.append(f"{name} is empty — {reason}")
        elif is_placeholder(value):
            errors.append(
                f"{name} still holds the .env.example placeholder ({value!r}) — {reason}"
            )

    for name in ("ENCRYPTION_KEY", "BLIND_INDEX_KEY"):
        value = env.get(name)
        if value and not is_fernet_key(value):
            errors.append(
                f"{name} is not a valid Fernet key (32 urlsafe-base64 bytes). "
                "Regenerate with: python scripts/preflight_check.py --generate"
            )

    if not any(env.get(k) for k in LLM_KEYS):
        errors.append(
            "No LLM provider key set — need at least one of: " + ", ".join(LLM_KEYS)
        )

    if env.get("ENVIRONMENT") != "production":
        warnings.append(
            "ENVIRONMENT is not 'production' in .env; docker-compose.yml overrides it "
            "to production for the backend regardless"
        )
    if env.get("DEBUG", "").lower() in ("1", "true", "yes"):
        errors.append("DEBUG must be false in production — it leaks internals in errors")
    if env.get("RATE_LIMITER_MODE", "redis") == "memory":
        errors.append(
            "RATE_LIMITER_MODE=memory raises at startup in production (unsafe across workers)"
        )
    if env.get("CIRCUIT_BREAKER_MODE", "redis") == "memory":
        warnings.append("CIRCUIT_BREAKER_MODE=memory is not shared across workers")

    cors = env.get("CORS_ORIGINS", "")
    if "localhost" in cors or "127.0.0.1" in cors:
        warnings.append(f"CORS_ORIGINS still contains a local origin: {cors}")

    if env.get("ENABLE_LEGACY_API_KEY", "").lower() in ("1", "true", "yes"):
        warnings.append("ENABLE_LEGACY_API_KEY=true bypasses the modern auth path")

    for name, reason in WARNING:
        if not env.get(name):
            warnings.append(f"{name} is empty — {reason}")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=str(REPO_ROOT / ".env"))
    parser.add_argument(
        "--generate", action="store_true", help="print a fresh set of secrets and exit"
    )
    args = parser.parse_args()

    if args.generate:
        generate_secrets()
        return 0

    env_path = Path(args.env_file)
    if not env_path.is_file():
        print(f"No env file at {env_path}")
        print("Create one with:  cp .env.example .env")
        return 1

    errors, warnings = check(parse_env_file(env_path))

    for warning in warnings:
        print(f"  WARN   {warning}")
    for error in errors:
        print(f"  BLOCK  {error}")

    print()
    if errors:
        print(f"{len(errors)} blocking problem(s) — the backend will not start.")
        print("Generate missing secrets with: python scripts/preflight_check.py --generate")
        return 1

    print(f"Ready to deploy. {len(warnings)} warning(s), no blocking problems.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
