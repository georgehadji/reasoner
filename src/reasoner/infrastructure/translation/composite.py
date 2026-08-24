"""CompositeTranslator: DeepL → LLM → identity fallback chain."""

from __future__ import annotations

import logging
from typing import Any

from reasoner.core.ports.translation_port import TranslationResult

logger = logging.getLogger(__name__)

_composite: CompositeTranslator | None = None


class CompositeTranslator:
    """Try DeepL first; fall back to LLM; fall back to identity with a warning."""

    def __init__(self, deepl: Any, llm: Any) -> None:
        self._deepl = deepl
        self._llm = llm

    async def translate(
        self,
        text: str,
        target_lang: str,
        source_lang: str | None = None,
    ) -> TranslationResult:
        reasons: list[str] = []

        if self._deepl is not None:
            try:
                raw = await self._deepl.translate(text, target_lang=target_lang, source_lang=source_lang)
                return TranslationResult(
                    text=raw.get("text", text),
                    detected_source_language=raw.get("detected_source_language", source_lang or "unknown"),
                )
            except Exception as exc:
                logger.warning("DeepL translation failed, trying LLM fallback: %s", exc)
                reasons.append(f"deepl: {exc}")
        else:
            reasons.append("deepl: not configured")

        if self._llm is not None:
            try:
                return await self._llm.translate(text, target_lang=target_lang, source_lang=source_lang)
            except Exception as exc:
                logger.warning("LLM translation failed, using identity fallback: %s", exc)
                reasons.append(f"llm: {exc}")
        else:
            reasons.append("llm: not configured")

        logger.warning("All translators failed; returning original text (pivot degraded to identity)")
        return TranslationResult(
            text=text,
            detected_source_language=source_lang or "unknown",
            degraded=True,
            degraded_reason="; ".join(reasons),
        )


def get_composite_translator(router: Any | None = None) -> CompositeTranslator:
    """Return (or lazily build) the process-wide CompositeTranslator.

    Pass *router* on the first call to wire in the LLM fallback.  Subsequent
    calls return the cached instance; *router* is ignored after initialisation.
    """
    global _composite
    if _composite is None:
        from reasoner.infrastructure.translation.deepl_client import DeepLClient
        from reasoner.infrastructure.translation.llm_translator import LLMTranslator

        deepl: DeepLClient | None = None
        try:
            deepl = DeepLClient()
            if not deepl.api_key:
                deepl = None
        except Exception:
            deepl = None

        llm: LLMTranslator | None = None
        if router is not None:
            try:
                llm = LLMTranslator(router)
            except Exception:
                pass

        _composite = CompositeTranslator(deepl=deepl, llm=llm)
    return _composite


def reset_composite_translator() -> None:
    """Reset the singleton (useful in tests)."""
    global _composite
    _composite = None
