"""Background task handlers for periodic maintenance."""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def _expire_tenant_dir(agent_dir: Path, agents_root: Path, retention_days: int) -> bool:
    """Delete *agent_dir* if nothing in it changed for *retention_days*. Blocking.

    The path is resolved and must sit inside *agents_root*, and a symlink is
    never followed, so a planted link cannot point deletion elsewhere.
    """
    if agent_dir.is_symlink():
        return False
    resolved = agent_dir.resolve()
    if resolved == agents_root.resolve() or not resolved.is_relative_to(agents_root.resolve()):
        return False
    newest = max(
        (p.lstat().st_mtime for p in resolved.rglob("*") if not p.is_symlink()),
        default=resolved.stat().st_mtime,
    )
    if time.time() - newest < retention_days * 86400:
        return False
    shutil.rmtree(resolved)
    return True


async def run_reservation_sweep() -> dict:
    """Release credit reservations of runs that died before settling.

    A reservation older than the pipeline's absolute timeout plus a margin
    cannot belong to a live run.
    """
    from datetime import UTC, datetime, timedelta

    from reasoner.api.dependencies import _get_credit_service
    from reasoner.core.constants_limits import PIPELINE_ABSOLUTE_TIMEOUT_SECONDS

    cutoff = datetime.now(UTC) - timedelta(seconds=PIPELINE_ABSOLUTE_TIMEOUT_SECONDS + 600)
    released = await _get_credit_service().release_orphaned_reservations(cutoff)
    logger.info("Reservation sweep: released=%d", released)
    return {"released": released}


async def run_neuro_maintenance() -> dict:
    """Run neuro lifecycle maintenance: archive hot→warm→cold sessions.

    Called by external scheduler (e.g., cron job hitting /api/admin/cron/neuro-maintenance).
    Sets the cron heartbeat metric on each successful run.

    Phase 1.7 fix: wires archive_hot_sessions / archive_warm_to_cold which
    previously had zero callers.
    """
    result: dict = {"archived_hot": 0, "moved_to_cold": 0, "expired_tenants": 0, "errors": []}

    try:
        from reasoner.core.constants_limits import NEURO_TENANT_RETENTION_DAYS
        from reasoner.neuro.config import NeuroConfig, load_config
        from reasoner.neuro.server import get_neuro_service
        from reasoner.neuro.sessions import SessionConfig, SessionManager

        config = load_config() or NeuroConfig()
        agents_dir = Path(config.data_dir) / "agents"

        if not agents_dir.exists():
            logger.info("Neuro maintenance: no agents directory (%s), skipping", agents_dir)
        else:
            tenants = get_neuro_service().tenants
            entries = await asyncio.to_thread(
                lambda: sorted(p for p in agents_dir.iterdir() if p.is_dir())
            )
            for agent_dir in entries:
                agent_id = agent_dir.name
                # This loop opens its own SessionManager, outside the tenant
                # manager's erase guard: archiving would write warm summaries
                # into the directory of an owner being (or just) erased.
                # Per-process, like the guard itself.
                if tenants.is_erased(agent_id):
                    logger.info("Neuro maintenance: skipping erased tenant %s", agent_id)
                    continue
                try:
                    if await asyncio.to_thread(
                        _expire_tenant_dir, agent_dir, agents_dir, NEURO_TENANT_RETENTION_DAYS
                    ):
                        result["expired_tenants"] += 1
                        logger.info("Neuro maintenance: removed idle tenant %s", agent_id)
                        continue
                    sessions = SessionManager(agent_dir, SessionConfig())

                    # Archive hot → warm
                    hot_archived = await sessions.archive_hot_sessions()
                    result["archived_hot"] += len(hot_archived)

                    # Move warm → cold
                    cold_moved = await asyncio.to_thread(sessions.archive_warm_to_cold)
                    result["moved_to_cold"] += len(cold_moved)

                except Exception as exc:
                    logger.warning("Neuro maintenance failed for agent %s: %s", agent_id, exc)
                    result["errors"].append({"agent": agent_id, "error": str(exc)})

    except Exception as exc:
        logger.warning("Neuro maintenance skipped (neuro not available): %s", exc)

    # Heartbeat metric — proves the cron ran
    try:
        from reasoner.infrastructure.metrics import REASONER_CRON_HEARTBEAT_TIMESTAMP
        REASONER_CRON_HEARTBEAT_TIMESTAMP.set(int(time.time()))
    except Exception:
        pass

    logger.info(
        "Neuro maintenance complete: archived_hot=%d, moved_to_cold=%d, errors=%d",
        result["archived_hot"], result["moved_to_cold"], len(result["errors"]),
    )
    return result
