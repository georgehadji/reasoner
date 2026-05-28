"""DeepL API client for text translation."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# DeepL free-tier keys end with ":fx"
from reasoner.core.constants import DEEPL_FREE_BASE_URL, DEEPL_PAID_BASE_URL

FREE_KEY_SUFFIX = ":fx"
FREE_BASE_URL = DEEPL_FREE_BASE_URL
PAID_BASE_URL = DEEPL_PAID_BASE_URL


def _get_base_url(api_key: str | None) -> str:
    """Select the correct DeepL endpoint based on the key type."""
    if api_key and api_key.endswith(FREE_KEY_SUFFIX):
        return FREE_BASE_URL
    return PAID_BASE_URL


class DeepLClient:
    """Lightweight async client for the DeepL REST API."""

    def __init__(self, api_key: str | None = None) -> None:
        from reasoner.core.settings import settings
        self.api_key = api_key or settings.DEEPL_API_KEY or os.getenv("DEEPL_API_KEY")
        self.base_url = _get_base_url(self.api_key)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def translate(
        self,
        text: str,
        target_lang: str,
        source_lang: str | None = None,
    ) -> dict[str, Any]:
        """
        Translate text via DeepL.

        Args:
            text: Text to translate.
            target_lang: Target language code (e.g., 'EN', 'DE', 'FR').
            source_lang: Source language code or None for auto-detection.

        Returns:
            Dict with keys: text (str), detected_source_language (str).

        Raises:
            RuntimeError: If translation fails or no API key is configured.
        """
        if not self.api_key:
            raise RuntimeError("DeepL API key not configured. Set DEEPL_API_KEY in .env")

        url = f"{self.base_url}/translate"
        payload: dict[str, Any] = {
            "text": [text],
            "target_lang": target_lang.upper(),
        }
        if source_lang:
            payload["source_lang"] = source_lang.upper()

        client = await self._get_client()
        resp = await client.post(
            url,
            data=payload,
            headers={"Authorization": f"DeepL-Auth-Key {self.api_key}"},
        )
        if resp.status_code != 200:
            logger.error("DeepL translate failed: %s %s", resp.status_code, resp.text)
            raise RuntimeError(f"DeepL API error {resp.status_code}: {resp.text}")

        data = resp.json()
        translations = data.get("translations", [])
        if not translations:
            raise RuntimeError("DeepL returned empty translations")

        first = translations[0]
        return {
            "text": first.get("text", ""),
            "detected_source_language": first.get("detected_source_language", source_lang or "unknown"),
        }

    async def health_check(self) -> bool:
        """Quick health check by querying usage."""
        if not self.api_key:
            return False
        try:
            url = f"{self.base_url}/usage"
            client = await self._get_client()
            resp = await client.get(
                url,
                headers={"Authorization": f"DeepL-Auth-Key {self.api_key}"},
            )
            return resp.status_code == 200
        except Exception as e:
            logger.warning("DeepL health check failed: %s", e)
            return False


# Global singleton for reuse within a process
_dpl_client: DeepLClient | None = None


def get_deepl_client() -> DeepLClient:
    """Return the shared DeepL client instance."""
    global _dpl_client
    if _dpl_client is None:
        _dpl_client = DeepLClient()
    return _dpl_client


def reset_deepl_client() -> None:
    """Reset the shared client (useful in tests)."""
    global _dpl_client
    _dpl_client = None
