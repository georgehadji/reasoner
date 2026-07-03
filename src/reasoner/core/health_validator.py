"""Startup health validation — auto-disables features when dependencies are missing.

This module runs at application startup to validate API keys and external
dependencies, then adjusts feature flags automatically. It provides:
- Zero-config graceful degradation
- Automatic feature gating based on credential availability
- Startup logging that tells the operator exactly what's active
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx

from reasoner.core.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    feature: str
    enabled: bool
    reason: str
    auto_corrected: bool = False


@dataclass
class HealthReport:
    results: list[ValidationResult] = field(default_factory=list)

    @property
    def all_healthy(self) -> bool:
        return all(r.enabled for r in self.results)

    def summary(self) -> str:
        lines = ["Feature Health Report:"]
        for r in self.results:
            status = "✅ ON" if r.enabled else "❌ OFF"
            correction = " (auto-corrected)" if r.auto_corrected else ""
            lines.append(f"  {status} {r.feature}: {r.reason}{correction}")
        return "\n".join(lines)


async def _check_openrouter_key(key: str | None) -> bool:
    """Quick validation that the OpenRouter key is not empty and syntactically valid."""
    if not key:
        return False
    if not key.startswith(("sk-or-", "sk-")):
        return False
    return True


async def _check_perplexity_key(key: str | None) -> bool:
    """Quick validation that the Perplexity key is not empty and syntactically valid."""
    if not key:
        return False
    if not key.startswith("pplx-"):
        return False
    return True


async def validate_all() -> HealthReport:
    """Run all health checks and return a report.

    This function is idempotent — calling it multiple times is safe.
    """
    report = HealthReport()

    # ── 1. OpenRouter (gate for Cohere rerank) ──
    or_key = settings.OPENROUTER_API_KEY
    or_ok = await _check_openrouter_key(or_key)

    # ── 2. Cohere Rerank ──
    if settings.COHERE_RERANK_ENABLED and not or_ok:
        # Auto-disable: no OpenRouter key means no rerank
        settings.COHERE_RERANK_ENABLED = False
        report.results.append(ValidationResult(
            feature="Cohere Rerank",
            enabled=False,
            reason="OPENROUTER_API_KEY missing or invalid — required for OpenRouter-hosted rerank",
            auto_corrected=True,
        ))
    else:
        report.results.append(ValidationResult(
            feature="Cohere Rerank",
            enabled=settings.COHERE_RERANK_ENABLED,
            reason="Active" if settings.COHERE_RERANK_ENABLED else "Disabled by configuration",
        ))

    # ── 3. Perplexity via OpenRouter Search ──
    report.results.append(ValidationResult(
        feature="Perplexity Search (OpenRouter)",
        enabled=or_ok,
        reason="OpenRouter key available — Perplexity search enabled" if or_ok else "OPENROUTER_API_KEY missing — web search will use Tavily/Brave fallback",
    ))

    # ── 4. Perplexity Embed (native API, opt-in via neuro.yaml) ──
    pplx_key = settings.PERPLEXITY_API_KEY or ""
    pplx_ok = await _check_perplexity_key(pplx_key)
    report.results.append(ValidationResult(
        feature="Perplexity Embed",
        enabled=pplx_ok,
        reason="PERPLEXITY_API_KEY available" if pplx_ok else "PERPLEXITY_API_KEY missing — will use fallback embedder",
    ))

    # ── 4. Document Semantic Retrieval ──
    if settings.DOCUMENT_SEMANTIC_RETRIEVAL_ENABLED and not or_ok:
        # Auto-disable: semantic retrieval needs an embedder, and the default
        # embedder path goes through OpenRouter
        settings.DOCUMENT_SEMANTIC_RETRIEVAL_ENABLED = False
        report.results.append(ValidationResult(
            feature="Document Semantic Retrieval",
            enabled=False,
            reason="OPENROUTER_API_KEY missing — semantic retrieval needs an embedder",
            auto_corrected=True,
        ))
    else:
        report.results.append(ValidationResult(
            feature="Document Semantic Retrieval",
            enabled=settings.DOCUMENT_SEMANTIC_RETRIEVAL_ENABLED,
            reason="Active" if settings.DOCUMENT_SEMANTIC_RETRIEVAL_ENABLED else "Disabled by configuration (opt-in)",
        ))

    # ── 5. Tavily Search ──
    tavily_ok = bool(settings.TAVILY_API_KEY and settings.TAVILY_SEARCH_ENABLED)
    report.results.append(ValidationResult(
        feature="Tavily Search",
        enabled=tavily_ok,
        reason="TAVILY_API_KEY configured and enabled" if tavily_ok else "TAVILY_API_KEY missing or disabled — will use Brave/Perplexity fallback",
    ))

    # ── 6. Brave Search ──
    brave_ok = bool(settings.BRAVE_SEARCH_API_KEY and settings.BRAVE_SEARCH_ENABLED)
    report.results.append(ValidationResult(
        feature="Brave Search",
        enabled=brave_ok,
        reason="BRAVE_SEARCH_API_KEY configured and enabled" if brave_ok else "BRAVE_SEARCH_API_KEY missing or disabled — will use Perplexity fallback",
    ))

    logger.info("\n%s", report.summary())
    return report
