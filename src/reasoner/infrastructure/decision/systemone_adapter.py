"""DecisionPort adapter: TypeSafe System One models through OpenRouter.

OpenRouter serves these on a separate endpoint, not chat completions:
POST https://openrouter.ai/api/v1/systemone. That is also why jev never
appears in GET /api/v1/models -- its absence there is not its absence.

Request:  {"model", "state", "questions": {key: {"type", "instructions", "criteria"?}}}
Response: {"model", "answers": {key: {...typed answer...}}, "usage": {"cost", ...}}

Uses the existing OPENROUTER_API_KEY; billing lands on that account, the same
as every other OpenRouter call. No TypeSafe account or key is involved.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from reasoner.core.ports.decision_port import DecisionResult, DecisionState

logger = logging.getLogger(__name__)

SYSTEMONE_URL = "https://openrouter.ai/api/v1/systemone"


class SystemOneAdapter:
    """Implements core.ports.decision_port.DecisionPort."""

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float,
        *,
        referer: str = "",
        app_title: str = "",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._model = model
        self._timeout = timeout_seconds
        self._headers = {"Authorization": f"Bearer {api_key}"}
        if referer:
            self._headers["HTTP-Referer"] = referer
        if app_title:
            self._headers["X-Title"] = app_title
        # Injected in tests (httpx.MockTransport); created lazily otherwise and
        # reused, so a request does not pay a fresh TLS handshake.
        self._client = client

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def decide(
        self,
        state: DecisionState,
        questions: dict[str, dict[str, Any]],
    ) -> DecisionResult:
        resp = await self._get_client().post(
            SYSTEMONE_URL,
            json={"model": self._model, "state": state, "questions": questions},
            headers=self._headers,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        answers = data.get("answers")
        # Every asked question must come back. A partial answer set is a
        # contract failure, not a smaller decision -- the caller would read a
        # missing key as a default and log a verdict nobody made.
        if not isinstance(answers, dict) or not set(questions) <= set(answers):
            missing = sorted(set(questions) - set(answers or {}))
            raise ValueError(f"System One response missing answers for {missing}")
        cost = (data.get("usage") or {}).get("cost")
        return DecisionResult(
            answers=answers,
            model=str(data.get("model") or self._model),
            cost_usd=float(cost) if isinstance(cost, int | float) else None,
        )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


def inject_decision_port() -> None:
    """Install the jev adapter as the DecisionPort when JEV_MODE uses jev
    ("active" or "shadow") and there is a key to call it with.

    Lives here rather than in the API lifespan for the reason
    inject_shared_cache_port does: api/__init__.py is under a pinned line-count
    cap whose rule is to shrink the module before growing it.

    Never raises. Not injecting is the off state, not a failure: with no port,
    hypergate/jev_router.py never calls jev and HyperGate's LLM sub-agents route.
    """
    from reasoner.core.constants import JEV_SHADOW_TIMEOUT_SECONDS
    from reasoner.core.ports.decision_port import set_decision_port
    from reasoner.core.settings import settings

    if settings.JEV_MODE not in ("active", "shadow"):
        return
    if not settings.OPENROUTER_API_KEY:
        logger.warning(
            "JEV_MODE=%s but OPENROUTER_API_KEY is unset; jev stays off", settings.JEV_MODE
        )
        return
    try:
        set_decision_port(
            SystemOneAdapter(
                settings.OPENROUTER_API_KEY,
                settings.JEV_MODEL,
                JEV_SHADOW_TIMEOUT_SECONDS,
                referer=settings.OPENROUTER_HTTP_REFERER,
                app_title=settings.OPENROUTER_APP_TITLE,
            )
        )
    except Exception as exc:
        logger.warning("Jev unavailable, staying off: %s", exc)
        return
    logger.info(
        "Jev ON (mode=%s, model=%s): HyperGate problems are sent to TypeSafe via OpenRouter%s",
        settings.JEV_MODE,
        settings.JEV_MODEL,
        "; jev routes, LLM sub-agents are the fallback" if settings.JEV_MODE == "active"
        else "; logged beside the LLM sub-agents, routing unchanged",
    )
