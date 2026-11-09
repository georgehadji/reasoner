"""Per-call authentication for MCP tools.

MCP tool calls are not FastAPI requests, so the HTTP dependency chain
(get_current_user, Depends(...)) does not apply here. Every tool still
authenticates through the same resolver the HTTP layer uses -- invoked
directly instead of through FastAPI's DI -- so there is no second key store
for the MCP surface, matching every other adapter in this plan.
"""

from __future__ import annotations

import os

from reasoner.domain.saas import User


class McpAuthError(Exception):
    """No usable credentials for this MCP call."""


def _bearer_token_from_context(ctx) -> str | None:
    """Pull a bearer token from wherever this transport carries one.

    Streamable-HTTP: the Authorization header on the underlying Starlette
    request. stdio: there is no per-call HTTP header, so REASONER_API_KEY
    from the server process's own environment stands in for it -- the whole
    process is the one authenticated caller.
    """
    request_context = ctx.request_context
    request = getattr(request_context, "request", None)
    if request is not None:
        header = request.headers.get("authorization", "")
        if header.lower().startswith("bearer "):
            return header[7:].strip() or None
        return None
    return os.environ.get("REASONER_API_KEY")


async def resolve_caller(ctx, *, scope: str | None = None) -> User:
    """Resolve the authenticated User for this tool call.

    With ``scope``, an API key must hold it, as ``require_key_scope`` demands
    over HTTP; session tokens pass, because scopes only narrow keys.

    Raises McpAuthError -- never HTTPException, since this module has no
    FastAPI dependency -- so FastMCP surfaces a clean tool-call error instead
    of a stack trace.
    """
    from reasoner.api.dependencies import _resolve_auth_token
    from reasoner.domain.api_keys import key_allows, looks_like_api_key

    token = _bearer_token_from_context(ctx)
    if not token:
        raise McpAuthError(
            "No credentials. Set REASONER_API_KEY in the server environment "
            "(stdio transport), or send Authorization: Bearer <key> (HTTP transport)."
        )
    try:
        user = await _resolve_auth_token(token)
    except Exception as exc:
        raise McpAuthError("Invalid or expired API key") from exc
    granted = getattr(user, "scopes", set())
    if scope and looks_like_api_key(token) and not key_allows(granted, scope):
        raise McpAuthError(f"API key lacks the '{scope}' scope")
    return user


__all__ = ["McpAuthError", "resolve_caller"]
