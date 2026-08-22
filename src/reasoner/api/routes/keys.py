"""API key status and validation endpoints."""

from __future__ import annotations

import asyncio
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request

from reasoner.api.auth_deps import optional_auth, require_auth, require_csrf
from reasoner.api.dependencies import check_rate_limit, get_current_user
from reasoner.domain.saas import User
from reasoner.auth import Scope
from reasoner.core.constants import TIMEOUTS, VALIDATION_TEST_MAX_TOKENS
from reasoner.infrastructure.llm.registry import (
    _REGISTRY,
    build_provider,
    direct_key_envs,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/keys/status")
async def get_api_keys_status(
    user: User = Depends(get_current_user),
    authenticated=Depends(optional_auth),
):
    """
    Get status of all configured LLM provider API keys.

    Returns which keys are set (without revealing values) and which
    providers are available for use.
    """
    env_status: dict[str, dict] = {}

    for model_id, cfg in _REGISTRY.items():
        env_var = cfg.get("env", "")
        if not env_var:
            continue

        if env_var not in env_status:
            key_value = os.environ.get(env_var, "")
            env_status[env_var] = {
                "is_set": bool(key_value),
                "key_length": len(key_value) if key_value else 0,
                "models": [],
                "is_local": cfg.get("is_local", False),
            }

        env_status[env_var]["models"].append(model_id)

    # Vendor-direct keys (DEEPSEEK_API_KEY, XAI_API_KEY) are deliberately not an
    # entry's "env" -- that field gates routing, and declaring them there would
    # make filter_routing() downgrade every DeepSeek/xAI role whenever only
    # OPENROUTER_API_KEY is set. They are still live credentials that
    # build_provider() prefers when present, so a status view enumerating "env"
    # alone silently omitted them.
    for env_var, models in direct_key_envs().items():
        if env_var in env_status:
            continue
        key_value = os.environ.get(env_var, "")
        env_status[env_var] = {
            "is_set": bool(key_value),
            "key_length": len(key_value) if key_value else 0,
            "models": list(models),
            "is_local": False,
            "optional": True,
        }

    total_providers = len(env_status)
    configured = sum(1 for s in env_status.values() if s["is_set"])

    # SECURITY: Admin-only endpoint to prevent reconnaissance.
    user_scopes = getattr(user, "scopes", set())
    if Scope.ADMIN.value not in user_scopes:
        raise HTTPException(status_code=403, detail="Admin scope required")

    return {
        "summary": {
            "total_providers": total_providers,
            "configured": configured,
            "missing": total_providers - configured,
        },
    }


@router.post("/api/keys/validate", dependencies=[Depends(check_rate_limit)])
async def validate_api_keys(
    request: Request,
    authenticated=Depends(require_auth),
    csrf_checked=Depends(require_csrf),
):
    """
    Pre-flight validation of API keys.

    Tests each configured provider with a minimal request to verify
    the API key is valid and the service is accessible.
    """
    results = {}
    tested_envs = set()

    for model_id, cfg in _REGISTRY.items():
        env_var = cfg.get("env", "")
        if not env_var or env_var in tested_envs:
            continue
        tested_envs.add(env_var)

        if cfg.get("is_local"):
            results[env_var] = {
                "status": "skipped",
                "reason": "Local provider - no API key needed",
            }
            continue

        key = os.environ.get(env_var, "")
        if not key:
            results[env_var] = {
                "status": "missing",
                "reason": f"Environment variable {env_var} not set",
            }
            continue

        try:
            provider = build_provider(model_id)
            await asyncio.wait_for(
                provider.complete(
                    system_prompt="Reply with: ok",
                    user_prompt="test",
                    max_tokens=VALIDATION_TEST_MAX_TOKENS,
                ),
                timeout=TIMEOUTS.MODEL_VALIDATION,
            )
            results[env_var] = {
                "status": "valid",
                "model_tested": model_id,
            }
        except asyncio.TimeoutError:
            results[env_var] = {
                "status": "timeout",
                "reason": "Provider did not respond within 10 seconds",
            }
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)[:200]
            results[env_var] = {
                "status": "error",
                "error_type": error_type,
                "reason": error_msg,
            }

    # Vendor-direct keys, which carry no entry "env" (see direct_key_envs).
    # build_provider() silently prefers them over the OpenRouter lane, so a
    # stale or revoked one 401s every call for that vendor while a preflight
    # that only walked "env" reported all-green. Unset is not a failure here --
    # these are an optional upgrade, not a requirement.
    for env_var, models in direct_key_envs().items():
        if env_var in tested_envs or not models:
            continue
        tested_envs.add(env_var)
        if not os.environ.get(env_var, ""):
            continue
        model_id = models[0]
        try:
            provider = build_provider(model_id)
            await asyncio.wait_for(
                provider.complete(
                    system_prompt="Reply with: ok",
                    user_prompt="test",
                    max_tokens=VALIDATION_TEST_MAX_TOKENS,
                ),
                timeout=TIMEOUTS.MODEL_VALIDATION,
            )
            results[env_var] = {"status": "valid", "model_tested": model_id}
        except asyncio.TimeoutError:
            results[env_var] = {
                "status": "timeout",
                "reason": "Provider did not respond within 10 seconds",
            }
        except Exception as e:
            results[env_var] = {
                "status": "error",
                "error_type": type(e).__name__,
                "reason": str(e)[:200],
            }

    valid_count = sum(1 for r in results.values() if r["status"] == "valid")
    total_count = len(results)

    # SECURITY: Do not expose per-provider validation details or model IDs
    return {
        "summary": {
            "valid": valid_count,
            "total": total_count,
            "all_valid": valid_count == total_count,
        },
    }
