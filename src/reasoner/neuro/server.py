"""
Neuro API Engine
Internal endpoints for recall, audit, and learning.
"""

import json
import time
import hashlib
import logging
import asyncio
import secrets
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
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
            l1_dir = data_dir / "cache" / "l1"
            l2_dir = data_dir / "cache" / "l2"

            for d in [l1_dir, l2_dir]:
                d.mkdir(parents=True, exist_ok=True)

            tenant = {
                "data_dir": data_dir,
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

def require_neuro_key(request: Request) -> None:
    """Gate /api/neuro/* to callers holding the shared internal key.

    The pipeline reaches these endpoints over loopback, but they are mounted
    on the public app: ungated, /audit is a free LLM proxy and /learn lets
    anyone write into a tenant's memory.

    An unset key is allowed through so local development works with no
    secrets configured; api/__init__.py refuses to start in production when
    the key is empty, so this branch is never the production posture.
    """
    expected = settings.neuro_internal_key
    if not expected:
        return
    provided = request.headers.get("X-Neuro-Key", "")
    if not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=403, detail="Neuro access required")


def tenant_key(owner: Optional[str], agent_id: Optional[str]) -> Optional[str]:
    """Scope a caller-supplied agent_id to the identity that owns it.

    agent_id is a conversation id that arrives straight from the request body,
    and it alone used to select the memory directory -- so anyone who learned
    another user's conversation id could recall or poison that conversation's
    memory through the Next proxy.

    Binding the owner into the key closes that by construction rather than by
    lookup: the same agent_id under two identities resolves to two different
    tenants, so a guessed id lands the guesser in their own namespace. No
    ownership table to keep in sync, and nothing to forget to check.

    Anonymous callers (owner=None) keep the bare agent_id namespace. They have
    no identity to protect, and they cannot reach an owned tenant because they
    cannot produce its "<owner>~" prefix.
    """
    if not owner:
        return agent_id
    return f"{owner}~{agent_id or 'default'}"


class NeuroService:
    """Owns the providers, tenants, and memory tiers.

    Reachable two ways, both hitting this same instance: in-process through
    MemoryPort (the pipeline) and over HTTP through the router below (the
    Next proxy, on behalf of the browser). One instance matters -- L1 is an
    in-memory cache backed by disk, so a second service object would hold a
    divergent copy of it until something forced a reload.
    """

    def __init__(self, config: Optional[NeuroConfig] = None):
        self.config = config or load_config()
        self.reasoner = create_resilient_reasoning(self.config.reasoning)
        self.embedder = create_resilient_embedding(self.config.embedding)
        self.tenants = TenantManager(self.config)

    # ── MemoryPort ────────────────────────────────────────────────────────
    async def recall(
        self,
        prompt: str,
        agent_id: Optional[str] = None,
        max_results: int = 5,
        owner: Optional[str] = None,
    ) -> list[dict]:
        resp = await self.recall_chunks(RecallRequest(
            prompt=prompt, agent_id=agent_id,
            max_results=max_results, compression="none",
        ), owner=owner)
        return [
            {"content": c.content, "source": c.source, "relevance": c.relevance}
            for c in resp.chunks
        ]

    async def learn(
        self,
        prompt: str,
        response: str,
        agent_id: Optional[str] = None,
        metadata: Optional[dict] = None,
        owner: Optional[str] = None,
    ) -> None:
        await self.ingest(LearnRequest(
            prompt=prompt, response=response,
            agent_id=agent_id, metadata=metadata or {},
        ), owner=owner)

    # ── Full request/response surface (shared with the router) ────────────
    async def health(self) -> NeuroHealthResponse:
        config, reasoner, embedder, tenants = (
            self.config, self.reasoner, self.embedder, self.tenants
        )
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

    async def recall_chunks(
        self, req: RecallRequest, owner: Optional[str] = None
    ) -> RecallResponse:
        config, embedder, tenants = self.config, self.embedder, self.tenants
        start = time.perf_counter()
        persona = get_persona(config, req.persona, req.agent_id)
        tenant = await tenants.get(tenant_key(owner, req.agent_id))
        l1, l2 = tenant["l1"], tenant["l2"]
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

        # L3: archived session summaries written by archive_hot_sessions().
        # Embeddings are sidecar-cached by content hash, so a cold scan only
        # calls the provider for summaries it has not seen before.
        # ponytail: linear directory scan on the recall path, bounded by
        # NEURO_RECALL_TIMEOUT_SECONDS. Fine for hundreds of summaries per
        # tenant; index the warm dir if a tenant ever accumulates thousands.
        remaining = req.max_results - len(all_chunks)
        if remaining > 0:
            try:
                all_chunks.extend(await l3_scan(
                    sessions.warm_dir, query_embedding, embedder.embed, top_k=remaining
                ))
            except Exception as exc:
                log.warning("L3 scan failed in recall: %s", exc)

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

    async def audit(
        self, req: AuditRequest, owner: Optional[str] = None
    ) -> AuditResponse:
        config, reasoner, tenants = self.config, self.reasoner, self.tenants
        start = time.perf_counter()
        persona = get_persona(config, req.persona, req.agent_id)
        tenant = await tenants.get(tenant_key(owner, req.agent_id))

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

    async def ingest(
        self, req: LearnRequest, owner: Optional[str] = None
    ) -> LearnResponse:
        embedder, tenants = self.embedder, self.tenants
        tenant = await tenants.get(tenant_key(owner, req.agent_id))
        result = tenant["sessions"].ingest(req.prompt, req.response, req.metadata)

        # Index the exchange for semantic recall. Without this nothing ever
        # writes L1/L2, so /recall degrades to HOT substring matching.
        #
        # The entry goes into both tiers deliberately: L1 is the hot subset
        # (24h TTL, 50 bundles, 0.75 threshold) that ages out, L2 the durable
        # index (500 entries, 0.5 threshold) that keeps it. Recall queries L1
        # first, so recent context matches at high precision before the wider
        # L2 scan. Both writes reuse the one embedding -- this costs a file
        # write, not a second provider call.
        #
        # Best-effort: a dead embedding provider must not fail the ingest.
        # ponytail: last-writer-wins on concurrent same-tenant learns can drop
        # an entry (L2Index rewrites index.json wholesale); add a per-tenant
        # lock if that shows up as measurable recall loss.
        try:
            content = f"User: {req.prompt}\nAssistant: {req.response}"
            embedding = await embedder.embed(content)
            source = f"session:{result['session_id']}"
            await tenant["l1"].add(content, source=source, embedding=embedding)
            await tenant["l2"].add(
                content,
                source=source,
                embedding=embedding,
                metadata=req.metadata or {},
            )
        except Exception as exc:
            log.warning("Memory indexing failed for learn (session %s): %s",
                        result["session_id"], exc)

        return LearnResponse(
            status="learned", session_id=result["session_id"],
            entry_number=result["entry_number"], agent_id=req.agent_id,
        )

    async def list_sessions(
        self,
        agent_id: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        owner: Optional[str] = None,
    ) -> dict:
        """List recent session entries for browsing memory."""
        tenant = await self.tenants.get(tenant_key(owner, agent_id))
        entries = tenant["sessions"].list_recent_entries(limit=limit, offset=offset)
        return {"entries": entries, "total": len(entries)}


_service: Optional[NeuroService] = None


def get_neuro_service() -> NeuroService:
    """Return the process-wide NeuroService, building it on first use.

    Injected as the MemoryPort at startup and used by create_neuro_router(),
    so the pipeline and the HTTP endpoints share one set of tenants and one
    L1 cache.
    """
    global _service
    if _service is None:
        _service = NeuroService()
    return _service


def create_neuro_router(config: Optional[NeuroConfig] = None) -> APIRouter:
    """Mount the HTTP surface over a NeuroService.

    Passing *config* builds an isolated service (tests); the default shares
    the process-wide one so HTTP and in-process callers see the same state.
    """
    service = NeuroService(config) if config is not None else get_neuro_service()

    router = APIRouter(prefix="/api/neuro", dependencies=[Depends(require_neuro_key)])

    # Imported lazily: reasoner.api imports this module, so a module-level
    # import would close the cycle.
    from reasoner.api.dependencies import get_optional_user

    async def _owner(user=Depends(get_optional_user)) -> Optional[str]:
        """Identity that owns the requested agent_id, or None if anonymous.

        Resolved from credentials by FastAPI -- never from the request body,
        or a caller could just claim someone else's owner and walk straight
        back into the isolation hole this closes.

        Must stay a real dependency: calling get_optional_user(request) by
        hand leaves its Depends(security) default unresolved, so every caller
        would look anonymous and the scoping would be silently inert.
        """
        if not user:
            return None
        return str(getattr(user, "id", "")) or None

    @router.get("/health", response_model=NeuroHealthResponse)
    async def health():
        return await service.health()

    @router.post("/recall", response_model=RecallResponse)
    async def recall(req: RecallRequest, owner: Optional[str] = Depends(_owner)):
        return await service.recall_chunks(req, owner=owner)

    @router.post("/audit", response_model=AuditResponse)
    async def audit(req: AuditRequest, owner: Optional[str] = Depends(_owner)):
        return await service.audit(req, owner=owner)

    @router.post("/learn")
    async def learn(req: LearnRequest, owner: Optional[str] = Depends(_owner)):
        return await service.ingest(req, owner=owner)

    @router.get("/sessions")
    async def list_sessions(
        agent_id: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        owner: Optional[str] = Depends(_owner),
    ):
        return await service.list_sessions(
            agent_id=agent_id, limit=limit, offset=offset, owner=owner
        )

    return router
