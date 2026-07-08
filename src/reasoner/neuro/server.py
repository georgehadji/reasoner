"""
Neuro API Engine
Internal endpoints for recall, audit, and learning.
"""

import json
import time
import hashlib
import logging
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from reasoner.neuro.config import (
    load_config, NeuroConfig, get_agent_data_dir, get_persona, PersonaConfig,
)
from reasoner.neuro.providers import create_resilient_reasoning, create_resilient_embedding
from reasoner.neuro.cache import L1Cache, L2Index, l3_scan, ContextChunk
from reasoner.neuro.sessions import SessionManager, SessionConfig
from reasoner.neuro.compression import smart_compress
from reasoner.core.rerank import rerank_memory_chunks
from reasoner.core.settings import settings
from reasoner.utils.json_safe import safe_json_loads, JSONDepthExceededError

log = logging.getLogger("neuro.api")

# Compression cache: (content_hash, level) → compressed string
_compression_cache: dict[str, str] = {}
_COMPRESSION_CACHE_MAX = 512


def _cached_compress(content: str, ext: str, level: str) -> str:
    key = hashlib.sha256(f"{content}\x00{ext}\x00{level}".encode()).hexdigest()[:20]
    if key not in _compression_cache:
        if len(_compression_cache) >= _COMPRESSION_CACHE_MAX:
            # Evict oldest quarter by removing arbitrary keys (dict is insertion-ordered)
            evict = list(_compression_cache)[:_COMPRESSION_CACHE_MAX // 4]
            for k in evict:
                del _compression_cache[k]
        _compression_cache[key] = smart_compress(content, ext=ext, level=level)
    return _compression_cache[key]


# ─────────────────────────────────────────────
#  Request/Response Models
# ─────────────────────────────────────────────

class NeuroHealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str
    reasoning: dict
    embedding: dict
    agents_configured: list[str]
    default_persona: str
    sessions: dict


class LearnRequest(BaseModel):
    prompt: str = Field(..., description="The user's prompt")
    response: str = Field(..., description="The agent's response")
    agent_id: Optional[str] = Field(None, description="Agent ID for tenant isolation")
    metadata: Optional[dict] = Field(None, description="Optional metadata")


class LearnResponse(BaseModel):
    status: str
    session_id: str
    entry_number: int
    agent_id: Optional[str]


class RecallRequest(BaseModel):
    prompt: str = Field(..., description="The prompt to search context for")
    agent_id: Optional[str] = Field(None, description="Agent ID for tenant isolation")
    persona: Optional[str] = Field(None, description="Persona mode")
    max_results: int = Field(5, ge=1, le=20)
    compression: str = Field("none", description="Compression level: none | minimal | aggressive")


class RecallChunkResponse(BaseModel):
    content: str
    source: str
    relevance: float
    cache_tier: str


class RecallResponse(BaseModel):
    chunks: list[RecallChunkResponse]
    total_found: int
    latency_ms: float
    cache_hits: dict
    agent_id: Optional[str]
    persona: str
    provider_used: str


class AuditRequest(BaseModel):
    prompt: str = Field(..., description="The user's original prompt")
    draft_response: str = Field(..., description="The agent's draft response")
    agent_id: Optional[str] = Field(None)
    persona: Optional[str] = Field(None, description="Persona mode override")


class AuditResponse(BaseModel):
    verdict: str
    confidence: float
    reason: str
    enrichment: Optional[str] = None
    latency_ms: float
    persona: str
    provider_used: str


# ─────────────────────────────────────────────
#  Tenant Manager
# ─────────────────────────────────────────────

class TenantManager:
    """Manages per-agent tenant state with LRU eviction to prevent unbounded growth.

    Phase 1.8 fix: caps active tenants, evicts idle tenants, and tracks
    last-access timestamps for TTL-based eviction.
    """

    MAX_TENANTS = 100
    IDLE_TTL_SECONDS = 1800  # 30 minutes

    def __init__(self, config: NeuroConfig):
        self.config = config
        self._tenants: dict[str, dict] = {}
        self._last_access: dict[str, float] = {}
        self._lock = asyncio.Lock()

    def _evict_stale_locked(self, now: float) -> int:
        """Evict tenants idle beyond IDLE_TTL_SECONDS. Caller must hold _lock."""
        evicted = 0
        stale = [k for k, t in self._last_access.items() if now - t > self.IDLE_TTL_SECONDS]
        for k in stale:
            del self._tenants[k]
            del self._last_access[k]
            evicted += 1
        return evicted

    def _evict_lru_locked(self) -> None:
        """Evict the least-recently-used tenant. Caller must hold _lock."""
        if not self._last_access:
            return
        oldest_key = min(self._last_access, key=lambda k: self._last_access[k])
        del self._tenants[oldest_key]
        del self._last_access[oldest_key]

    async def get(self, agent_id: Optional[str] = None) -> dict:
        key = agent_id or "default"
        now = time.monotonic()
        async with self._lock:
            # TTL eviction pass
            self._evict_stale_locked(now)

            if key in self._tenants:
                self._last_access[key] = now
                return self._tenants[key]

            # LRU cap: evict oldest if at capacity
            if len(self._tenants) >= self.MAX_TENANTS:
                self._evict_lru_locked()

            data_dir = get_agent_data_dir(self.config, agent_id)
            memory_dir = data_dir / "memory"
            l1_dir = data_dir / "cache" / "l1"
            l2_dir = data_dir / "cache" / "l2"

            for d in [memory_dir, l1_dir, l2_dir]:
                d.mkdir(parents=True, exist_ok=True)

            tenant = {
                "data_dir": data_dir,
                "memory_dir": memory_dir,
                "l1": L1Cache(l1_dir, self.config.cache),
                "l2": L2Index(l2_dir, self.config.cache),
                "sessions": SessionManager(data_dir, SessionConfig()),
            }
            self._tenants[key] = tenant
            self._last_access[key] = now
            return tenant

    @property
    def active_tenants(self) -> list[str]:
        return list(self._tenants.keys())


# ─────────────────────────────────────────────
#  Prompts
# ─────────────────────────────────────────────

BASE_AUDIT_PROMPT = """You are Neuro, a memory coprocessor for reasoning agents.
Review the agent's draft response against the user's prompt and any memory context.

Respond with EXACTLY this JSON format (no markdown):
{{
    "verdict": "PASS|ENRICH|WARN|BLOCK",
    "confidence": 0.0-1.0,
    "reason": "brief explanation",
    "enrichment": "additional context if ENRICH, otherwise null"
}}"""

def build_audit_system_prompt(persona: PersonaConfig) -> str:
    prompt = BASE_AUDIT_PROMPT
    if persona.custom_system_prompt:
        prompt += f"\n\nADDITIONAL INSTRUCTIONS ({persona.name.upper()} MODE):\n{persona.custom_system_prompt}"
    return prompt


# ─────────────────────────────────────────────
#  Router Factory
# ─────────────────────────────────────────────

def create_neuro_router(config: Optional[NeuroConfig] = None) -> APIRouter:
    if config is None:
        config = load_config()

    router = APIRouter(prefix="/api/neuro")
    reasoner = create_resilient_reasoning(config.reasoning)
    embedder = create_resilient_embedding(config.embedding)
    tenants = TenantManager(config)

    @router.get("/health", response_model=NeuroHealthResponse)
    async def health():
        r_ok = await reasoner.health_check()
        e_ok = await embedder.health_check()
        total_sessions = {"hot": 0, "warm": 0, "cold": 0}
        tenant_snapshot = list(tenants._tenants.values())
        for t in tenant_snapshot:
            s = t["sessions"].stats
            total_sessions["hot"] += s["hot_sessions"]
            total_sessions["warm"] += s["warm_sessions"]
            total_sessions["cold"] += s["cold_sessions"]

        return NeuroHealthResponse(
            status="ok" if (r_ok and e_ok) else "degraded",
            version="2.1.0",
            timestamp=datetime.now(timezone.utc).isoformat(),
            reasoning={**reasoner.status, "healthy": r_ok},
            embedding={**embedder.status, "healthy": e_ok},
            agents_configured=list(config.agents.keys()) + tenants.active_tenants,
            default_persona="default",
            sessions=total_sessions,
        )

    @router.post("/recall", response_model=RecallResponse)
    async def recall(req: RecallRequest):
        start = time.perf_counter()
        persona = get_persona(config, req.persona, req.agent_id)
        tenant = await tenants.get(req.agent_id)
        l1, l2 = tenant["l1"], tenant["l2"]
        memory_dir = tenant["memory_dir"]
        sessions = tenant["sessions"]

        all_chunks = []
        # HOT search
        hot_results = sessions.search_hot(req.prompt, max_results=3)
        for hr in hot_results:
            all_chunks.append(ContextChunk(
                content=f"[{hr['timestamp'][:16]}] User: {hr['prompt']}\nAgent: {hr['response']}",
                source=f"recent-session:{hr['session_id']}",
                relevance=0.95, cache_tier="HOT",
            ))

        query_embedding = await embedder.embed(req.prompt)
        
        # L1/L2 search
        remaining = req.max_results - len(all_chunks)
        if remaining > 0:
            all_chunks.extend(l1.search(query_embedding, top_k=remaining, persona=persona))
        
        remaining = req.max_results - len(all_chunks)
        if remaining > 0:
            all_chunks.extend(l2.search(query_embedding, top_k=remaining, persona=persona))

        # Optional: cross-encoder rerank for higher precision
        if len(all_chunks) > 1 and settings.COHERE_RERANK_ENABLED:
            try:
                all_chunks = await rerank_memory_chunks(
                    req.prompt, all_chunks, top_k=req.max_results
                )
            except Exception as exc:
                log.warning("Memory rerank failed in recall: %s", exc)

        # Apply compression if requested (results are cached by content hash + level)
        if req.compression != "none":
            for chunk in all_chunks:
                ext = ""
                if ":" in chunk.source:
                    source_parts = chunk.source.split(":")
                    if "." in source_parts[-1]:
                        ext = source_parts[-1].split(".")[-1]
                chunk.content = _cached_compress(chunk.content, ext=ext, level=req.compression)

        latency = (time.perf_counter() - start) * 1000
        return RecallResponse(
            chunks=[RecallChunkResponse(**c.to_dict()) for c in all_chunks],
            total_found=len(all_chunks),
            latency_ms=round(latency, 1),
            cache_hits={}, agent_id=req.agent_id, persona=persona.name,
            provider_used=embedder.active_label,
        )

    @router.post("/audit", response_model=AuditResponse)
    async def audit(req: AuditRequest):
        start = time.perf_counter()
        persona = get_persona(config, req.persona, req.agent_id)
        tenant = await tenants.get(req.agent_id)
        
        system_prompt = build_audit_system_prompt(persona)
        user_prompt = f"PROMPT:\n{req.prompt}\n\nDRAFT RESPONSE:\n{req.draft_response}"

        try:
            raw = await reasoner.generate(user_prompt, system=system_prompt)
            result = safe_json_loads(raw.strip().strip("`").replace("json", "", 1).strip(), max_depth=50)
            return AuditResponse(
                verdict=result.get("verdict", "PASS"),
                confidence=result.get("confidence", 0.5),
                reason=result.get("reason", ""),
                enrichment=result.get("enrichment"),
                latency_ms=round((time.perf_counter() - start) * 1000, 1),
                persona=persona.name, provider_used=reasoner.active_label,
            )
        except Exception as e:
            log.warning("Audit failed (returning WARN): %s", e)
            return AuditResponse(
                verdict="WARN", confidence=0.0, reason=f"Audit parse failed: {e}",
                latency_ms=round((time.perf_counter() - start) * 1000, 1),
                persona=persona.name, provider_used=reasoner.active_label,
            )

    @router.post("/learn")
    async def learn(req: LearnRequest):
        tenant = await tenants.get(req.agent_id)
        result = tenant["sessions"].ingest(req.prompt, req.response, req.metadata)
        return LearnResponse(
            status="learned", session_id=result["session_id"],
            entry_number=result["entry_number"], agent_id=req.agent_id,
        )

    @router.get("/sessions")
    async def list_sessions(
        agent_id: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ):
        """List recent session entries for browsing memory."""
        tenant = await tenants.get(agent_id)
        entries = tenant["sessions"].list_recent_entries(limit=limit, offset=offset)
        return {"entries": entries, "total": len(entries)}

    return router
