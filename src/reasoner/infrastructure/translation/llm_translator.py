"""LLM-backed translation adapter — key-free fallback for the CompositeTranslator."""

from __future__ import annotations

import logging
from typing import Any

from reasoner.core.ports.translation_port import TranslationResult

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a faithful translator. "
    "Translate the user's text into the requested language. "
    "Preserve meaning, structure, markdown formatting, citations, URLs, and "
    "epistemic tags (VERIFIED, HYPOTHESIS, UNKNOWN) exactly as written. "
    "Do not editorialize, add, or omit content. "
    "Respond with only the translated text."
)


class LLMTranslator:
    """Translates via any LLMPort-compatible router using the 'translation' role."""

    def __init__(self, router: Any) -> None:
        self._router = router

    async def translate(
        self,
        text: str,
        target_lang: str,
        source_lang: str | None = None,
    ) -> TranslationResult:
        from_clause = f" from {source_lang}" if source_lang else ""
        user_prompt = (
            f"Translate the following text{from_clause} into {target_lang}:\n\n{text}"
        )
        translated, _ = await self._router.call(
            role="translation",
            system_prompt=_SYSTEM,
            user_prompt=user_prompt,
            max_tokens=4096,
            temperature=0.1,
        )
        return TranslationResult(
            text=translated.strip(),
            detected_source_language=source_lang or "unknown",
        )
