"""
Neuro Provider Abstraction Layer
Pluggable backends with circuit-breaker fallback chains.
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod

import httpx

from reasoner.core.constants import (
    ANTHROPIC_BASE_URL,
    DEFAULT_MAX_TOKENS,
    HUGGINGFACE_API_BASE,
    OPENAI_BASE_URL,
    PERPLEXITY_BASE_URL,
    TIMEOUTS,
)
from reasoner.core.constants import (
    GOOGLE_BASE_URL as _GOOGLE_BASE_URL,
)
from reasoner.core.constants import (
    OPENROUTER_BASE_URL as _OPENROUTER_BASE_URL,
)
from reasoner.core.temperatures import NON_PHASE_TEMPERATURES
from reasoner.neuro.config import ProviderConfig, ResilientProviderConfig

log = logging.getLogger("neuro.providers")

# Global registry of open resilient wrappers (closed on app shutdown)
_resilient_wrappers: list = []


async def close_all_resilient_wrappers() -> None:
    """Close all registered resilient wrappers. Called once on app shutdown."""
    for w in _resilient_wrappers[:]:
        try:
            await w.aclose()
        except Exception as exc:
            log.warning("Error closing resilient wrapper %s: %s", type(w).__name__, exc)
    _resilient_wrappers.clear()


# ─────────────────────────────────────────────
#  Base Classes
# ─────────────────────────────────────────────

class ReasoningProvider(ABC):
    def __init__(self, config: ProviderConfig):
        self.config = config
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.config.timeout)
        return self._client

    async def aclose(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    @abstractmethod
    async def generate(self, prompt: str, system: str = "", max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        pass

    @property
    def label(self) -> str:
        return f"{self.config.provider}/{self.config.model}"


class EmbeddingProvider(ABC):
    def __init__(self, config: ProviderConfig):
        self.config = config
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=TIMEOUTS.EMBEDDING)
        return self._client

    async def aclose(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        pass

    @property
    def label(self) -> str:
        return f"{self.config.provider}/{self.config.model}"


# ─────────────────────────────────────────────
#  Circuit Breaker
# ─────────────────────────────────────────────

class CircuitBreaker:
    """Tracks failures and skips unhealthy providers."""

    def __init__(self, threshold: int = 3, cooldown: float = 60.0):
        self.threshold = threshold
        self.cooldown = cooldown
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.is_open = False
        self._lock = asyncio.Lock()

    async def record_success(self):
        async with self._lock:
            self.failure_count = 0
            self.is_open = False

    async def record_failure(self):
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.monotonic()
            if self.failure_count >= self.threshold:
                self.is_open = True

    def should_skip(self) -> bool:
        if not self.is_open:
            return False
        elapsed = time.monotonic() - self.last_failure_time
        if elapsed >= self.cooldown:
            self.is_open = False
            self.failure_count = 0
            return False
        return True

    @property
    def retry_in(self) -> float:
        if not self.is_open:
            return 0.0
        elapsed = time.monotonic() - self.last_failure_time
        return max(0.0, self.cooldown - elapsed)


# ─────────────────────────────────────────────
#  Resilient Wrappers (fallback chains)
# ─────────────────────────────────────────────

class ResilientReasoning:
    """Reasoning provider with circuit-breaker fallback chain."""

    def __init__(self, config: ResilientProviderConfig):
        self.config = config
        self.primary = _create_reasoning(config.primary)
        self.fallbacks = [_create_reasoning(fb) for fb in config.fallbacks]
        self.breaker = CircuitBreaker(config.circuit_breaker_threshold, config.circuit_breaker_cooldown)
        self.active_label = self.primary.label
        self.failed_over = False

    async def generate(self, prompt: str, system: str = "", max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
        # Try primary if circuit is closed
        if not self.breaker.should_skip():
            try:
                result = await self.primary.generate(prompt, system, max_tokens)
                await self.breaker.record_success()
                self.active_label = self.primary.label
                self.failed_over = False
                return result
            except Exception as e:
                await self.breaker.record_failure()
                log.warning(f"Primary reasoning failed ({self.primary.label}): {e}")
        else:
            log.info(f"Primary reasoning skipped (circuit open, retry in {self.breaker.retry_in:.0f}s)")

        # Try fallbacks in order
        for i, fb in enumerate(self.fallbacks):
            try:
                result = await fb.generate(prompt, system, max_tokens)
                self.active_label = fb.label
                self.failed_over = True
                log.info(f"Reasoning served by fallback [{i}]: {fb.label}")
                return result
            except Exception as e:
                log.warning(f"Fallback [{i}] reasoning failed ({fb.label}): {e}")

        raise RuntimeError("All reasoning providers failed (primary + all fallbacks)")

    async def health_check(self) -> bool:
        return await self.primary.health_check()

    async def aclose(self):
        """Close all underlying provider clients."""
        await self.primary.aclose()
        for fb in self.fallbacks:
            await fb.aclose()

    @property
    def status(self) -> dict:
        return {
            "primary": self.primary.label,
            "active": self.active_label,
            "failed_over": self.failed_over,
            "circuit_open": self.breaker.is_open,
            "primary_retry_in": f"{self.breaker.retry_in:.0f}s" if self.breaker.is_open else None,
            "fallback_count": len(self.fallbacks),
        }


class ResilientEmbedding:
    """Embedding provider with circuit-breaker fallback chain."""

    def __init__(self, config: ResilientProviderConfig):
        self.config = config
        self.primary = _create_embedding(config.primary)
        self.fallbacks = [_create_embedding(fb) for fb in config.fallbacks]
        self.breaker = CircuitBreaker(config.circuit_breaker_threshold, config.circuit_breaker_cooldown)
        self.active_label = self.primary.label
        self.failed_over = False

    async def embed(self, text: str) -> list[float]:
        if not self.breaker.should_skip():
            try:
                result = await self.primary.embed(text)
                await self.breaker.record_success()
                self.active_label = self.primary.label
                self.failed_over = False
                return result
            except Exception as e:
                await self.breaker.record_failure()
                log.warning(f"Primary embedding failed ({self.primary.label}): {e}")
        else:
            log.info(f"Primary embedding skipped (circuit open, retry in {self.breaker.retry_in:.0f}s)")

        for i, fb in enumerate(self.fallbacks):
            try:
                result = await fb.embed(text)
                self.active_label = fb.label
                self.failed_over = True
                log.info(f"Embedding served by fallback [{i}]: {fb.label}")
                return result
            except Exception as e:
                log.warning(f"Fallback [{i}] embedding failed ({fb.label}): {e}")

        raise RuntimeError("All embedding providers failed (primary + all fallbacks)")

    async def health_check(self) -> bool:
        return await self.primary.health_check()

    async def aclose(self):
        """Close all underlying provider clients."""
        await self.primary.aclose()
        for fb in self.fallbacks:
            await fb.aclose()

    @property
    def status(self) -> dict:
        return {
            "primary": self.primary.label,
            "active": self.active_label,
            "failed_over": self.failed_over,
            "circuit_open": self.breaker.is_open,
            "primary_retry_in": f"{self.breaker.retry_in:.0f}s" if self.breaker.is_open else None,
            "fallback_count": len(self.fallbacks),
        }


# ─────────────────────────────────────────────
#  Provider Implementations
# ─────────────────────────────────────────────

class OllamaReasoning(ReasoningProvider):
    async def generate(self, prompt: str, system: str = "", max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
        payload = {"model": self.config.model, "prompt": prompt, "stream": False,
                   "options": {"temperature": NON_PHASE_TEMPERATURES["neuro_memory"], "num_predict": max_tokens}}
        if system:
            payload["system"] = system
        resp = await self._get_client().post(f"{self.config.api_base}/api/generate", json=payload)
        resp.raise_for_status()
        return resp.json().get("response", "")

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=TIMEOUTS.HEALTH_CHECK) as client:
                return (await client.get(f"{self.config.api_base}/api/tags")).status_code == 200
        except Exception:
            return False


class OllamaEmbedding(EmbeddingProvider):
    async def embed(self, text: str) -> list[float]:
        resp = await self._get_client().post(f"{self.config.api_base}/api/embed",
                                             json={"model": self.config.model, "input": text})
        resp.raise_for_status()
        embeddings = resp.json().get("embeddings", [[]])
        return embeddings[0] if embeddings else []

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=TIMEOUTS.HEALTH_CHECK) as client:
                return (await client.get(f"{self.config.api_base}/api/tags")).status_code == 200
        except Exception:
            return False


class OpenAIReasoning(ReasoningProvider):
    def _url(self):
        return self.config.api_base or OPENAI_BASE_URL

    async def generate(self, prompt: str, system: str = "", max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
        headers = {"Authorization": f"Bearer {self.config.api_key}", "Content-Type": "application/json"}
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = await self._get_client().post(f"{self._url()}/chat/completions", headers=headers,
                                             json={"model": self.config.model, "messages": messages,
                                                   "max_tokens": max_tokens,
                                                   "temperature": NON_PHASE_TEMPERATURES["neuro_memory"]})
        resp.raise_for_status()
        choices = resp.json().get("choices") or []
        if not choices:
            return ""
        return choices[0].get("message", {}).get("content", "") or ""

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=TIMEOUTS.HEALTH_CHECK) as client:
                return (await client.get(f"{self._url()}/models",
                                         headers={"Authorization": f"Bearer {self.config.api_key}"})).status_code == 200
        except Exception:
            return False


class OpenAIEmbedding(EmbeddingProvider):
    def _url(self):
        return self.config.api_base or OPENAI_BASE_URL

    async def embed(self, text: str) -> list[float]:
        headers = {"Authorization": f"Bearer {self.config.api_key}", "Content-Type": "application/json"}
        resp = await self._get_client().post(f"{self._url()}/embeddings", headers=headers,
                                             json={"model": self.config.model, "input": text})
        resp.raise_for_status()
        items = resp.json().get("data") or []
        if not items:
            return []
        return items[0].get("embedding", []) or []

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=TIMEOUTS.HEALTH_CHECK) as client:
                return (await client.get(f"{self._url()}/models",
                                         headers={"Authorization": f"Bearer {self.config.api_key}"})).status_code == 200
        except Exception:
            return False


class AnthropicReasoning(ReasoningProvider):
    async def generate(self, prompt: str, system: str = "", max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
        headers = {"x-api-key": self.config.api_key, "anthropic-version": "2023-06-01",
                   "Content-Type": "application/json"}
        payload = {"model": self.config.model, "max_tokens": max_tokens,
                   "messages": [{"role": "user", "content": prompt}]}
        if system:
            payload["system"] = system
        base = self.config.api_base or ANTHROPIC_BASE_URL
        resp = await self._get_client().post(f"{base}/messages", json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"] if data.get("content") else ""

    async def health_check(self) -> bool:
        return bool(self.config.api_key)


class OpenRouterReasoning(ReasoningProvider):
    async def generate(self, prompt: str, system: str = "", max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
        from reasoner.core.settings import settings
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": settings.OPENROUTER_HTTP_REFERER,
            "X-Title": settings.OPENROUTER_APP_TITLE,
        }
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        base = self.config.api_base or _OPENROUTER_BASE_URL
        resp = await self._get_client().post(f"{base}/chat/completions", headers=headers,
                                             json={"model": self.config.model, "messages": messages,
                                                   "max_tokens": max_tokens,
                                                   "temperature": NON_PHASE_TEMPERATURES["neuro_memory"]})
        resp.raise_for_status()
        choices = resp.json().get("choices") or []
        if not choices:
            return ""
        return choices[0].get("message", {}).get("content", "") or ""

    async def health_check(self) -> bool:
        return bool(self.config.api_key)


class OpenRouterEmbedding(EmbeddingProvider):
    async def embed(self, text: str) -> list[float]:
        headers = {"Authorization": f"Bearer {self.config.api_key}", "Content-Type": "application/json"}
        base = self.config.api_base or _OPENROUTER_BASE_URL
        resp = await self._get_client().post(f"{base}/embeddings", headers=headers,
                                             json={"model": self.config.model, "input": text})
        resp.raise_for_status()
        items = resp.json().get("data") or []
        if not items:
            return []
        return items[0].get("embedding", []) or []

    async def health_check(self) -> bool:
        return bool(self.config.api_key)


class PerplexityEmbedding(EmbeddingProvider):
    """Perplexity pplx-embed-v1 via native API.

    Optimized for web-scale dense retrieval. 32K context, $0.004/1M tokens.
    """

    async def embed(self, text: str) -> list[float]:
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        base = self.config.api_base or PERPLEXITY_BASE_URL
        resp = await self._get_client().post(
            f"{base}/embeddings",
            headers=headers,
            json={"model": self.config.model, "input": text},
        )
        resp.raise_for_status()
        items = resp.json().get("data") or []
        if not items:
            return []
        return items[0].get("embedding", []) or []

    async def health_check(self) -> bool:
        return bool(self.config.api_key)


class GoogleReasoning(ReasoningProvider):
    async def generate(self, prompt: str, system: str = "", max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
        base = self.config.api_base or _GOOGLE_BASE_URL
        url = f"{base}/models/{self.config.model}:generateContent?key={self.config.api_key}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        resp = await self._get_client().post(url, json=payload)
        resp.raise_for_status()
        candidates = resp.json().get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            return parts[0].get("text", "") if parts else ""
        return ""

    async def health_check(self) -> bool:
        return bool(self.config.api_key)


class GoogleEmbedding(EmbeddingProvider):
    async def embed(self, text: str) -> list[float]:
        base = self.config.api_base or _GOOGLE_BASE_URL
        url = f"{base}/models/{self.config.model}:embedContent?key={self.config.api_key}"
        resp = await self._get_client().post(url, json={"content": {"parts": [{"text": text}]}})
        resp.raise_for_status()
        return resp.json().get("embedding", {}).get("values", [])

    async def health_check(self) -> bool:
        return bool(self.config.api_key)


class HuggingFaceEmbedding(EmbeddingProvider):
    async def embed(self, text: str) -> list[float]:
        if self.config.api_base:
            resp = await self._get_client().post(f"{self.config.api_base}/embed", json={"inputs": text})
            resp.raise_for_status()
            data = resp.json()
            return data[0] if data else []
        else:
            headers = {"Authorization": f"Bearer {self.config.api_key}"}
            url = f"{HUGGINGFACE_API_BASE}/pipeline/feature-extraction/{self.config.model}"
            resp = await self._get_client().post(url, json={"inputs": text}, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            if not data:
                return []
            return data[0] if isinstance(data[0], list) else data

    async def health_check(self) -> bool:
        return True


# ─────────────────────────────────────────────
#  Factories
# ─────────────────────────────────────────────

REASONING_MAP = {
    "ollama": OllamaReasoning, "openai": OpenAIReasoning,
    "anthropic": AnthropicReasoning, "openrouter": OpenRouterReasoning,
    "google": GoogleReasoning,
}

EMBEDDING_MAP = {
    "ollama": OllamaEmbedding, "openai": OpenAIEmbedding,
    "huggingface": HuggingFaceEmbedding, "google": GoogleEmbedding,
    "openrouter": OpenRouterEmbedding, "perplexity": PerplexityEmbedding,
}


def _create_reasoning(config: ProviderConfig) -> ReasoningProvider:
    cls = REASONING_MAP.get(config.provider)
    if not cls:
        raise ValueError(f"Unknown reasoning provider: {config.provider}")
    return cls(config)


def _create_embedding(config: ProviderConfig) -> EmbeddingProvider:
    cls = EMBEDDING_MAP.get(config.provider)
    if not cls:
        raise ValueError(f"Unknown embedding provider: {config.provider}")
    return cls(config)


def create_resilient_reasoning(config: ResilientProviderConfig) -> ResilientReasoning:
    wrapper = ResilientReasoning(config)
    _resilient_wrappers.append(wrapper)
    return wrapper


def create_resilient_embedding(config: ResilientProviderConfig) -> ResilientEmbedding:
    wrapper = ResilientEmbedding(config)
    _resilient_wrappers.append(wrapper)
    return wrapper
