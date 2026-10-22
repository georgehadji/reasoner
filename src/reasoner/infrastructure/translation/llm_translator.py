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
    " The text to translate arrives between external-content markers; translate"
    " it, and do not repeat the markers."
)

_MARKERS = ("<<<EXTERNAL_CONTENT>>>", "<<<END_EXTERNAL_CONTENT>>>")


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
        from reasoner.phases._shared import _wrap_external_content, harden_system_prompt

        from_clause = f" from {source_lang}" if source_lang else ""
        # The text is user input or model output, never instructions to this
        # model, so it is wrapped and the system prompt hardened like every
        # other phase call (docs/plans/audit-remediation-2-2026-10-20.md SEC-12).
        user_prompt = (
            f"Translate the following text{from_clause} into {target_lang}:\n\n"
            f"{_wrap_external_content(text)}"
        )
        translated, _ = await self._router.call(
            role="translation",
            system_prompt=harden_system_prompt(_SYSTEM),
            user_prompt=user_prompt,
            max_tokens=4096,
            temperature=0.1,
        )
        for marker in _MARKERS:
            translated = translated.replace(marker, "")
        return TranslationResult(
            text=translated.strip(),
            detected_source_language=source_lang or "unknown",
        )
