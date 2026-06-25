"""Port for translation — CompositeTranslator implements this."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class TranslationResult:
    text: str
    detected_source_language: str


@runtime_checkable
class TranslationPort(Protocol):
    async def translate(
        self,
        text: str,
        target_lang: str,
        source_lang: str | None = None,
    ) -> TranslationResult: ...
