"""Port for translation — CompositeTranslator implements this."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class TranslationResult:
    text: str
    detected_source_language: str
    # True when no translator succeeded and *text* is the untranslated input.
    # Without this the identity fallback is indistinguishable from a real
    # translation, so callers silently shipped source-language text as if it
    # had been translated.
    degraded: bool = False
    degraded_reason: str = ""


@runtime_checkable
class TranslationPort(Protocol):
    async def translate(
        self,
        text: str,
        target_lang: str,
        source_lang: str | None = None,
    ) -> TranslationResult: ...
