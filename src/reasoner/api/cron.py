"""Background task handlers for periodic maintenance."""

from __future__ import annotations

import logging
import time

from reasoner.core.settings import settings
from reasoner.infrastructure.persistence.quota_repo_postgres import PostgresQuotaRepository

logger = logging.getLogger(__name__)


async def reset_all_quotas_monthly() -> None:
    """Reset all usage_quotas at month start. Called by external scheduler."""
    repo = PostgresQuotaRepository(settings.DATABASE_URL)
    pool = await repo._get_pool()
    result = await pool.execute(
        "UPDATE usage_quotas SET used_queries = 0, period_start = date_trunc('month', (NOW() AT TIME ZONE 'UTC')), "
        "updated_at = (NOW() AT TIME ZONE 'UTC') WHERE period_start < date_trunc('month', (NOW() AT TIME ZONE 'UTC'))"
    )
    logger.info("Monthly quota reset complete: %s", result)


async def run_neuro_maintenance() -> dict:
    """Run neuro lifecycle maintenance: archive hot→warm→cold sessions.

    Called by external scheduler (e.g., cron job hitting /api/admin/cron/neuro-maintenance).
    Sets the cron heartbeat metric on each successful run.

    Phase 1.7 fix: wires archive_hot_sessions / archive_warm_to_cold which
    previously had zero callers.
    """
    result: dict = {"archived_hot": 0, "moved_to_cold": 0, "errors": []}

    try:
        from pathlib import Path

        from reasoner.neuro.config import NeuroConfig, load_config
        from reasoner.neuro.sessions import SessionConfig, SessionManager

        config = load_config() or NeuroConfig()
        agents_dir = Path(config.data_dir) / "agents"

        if not agents_dir.exists():
            logger.info("Neuro maintenance: no agents directory (%s), skipping", agents_dir)
        else:
            for agent_dir in sorted(agents_dir.iterdir()):
                if not agent_dir.is_dir():
                    continue
                agent_id = agent_dir.name
                try:
                    sessions = SessionManager(agent_dir, SessionConfig())

                    # Archive hot → warm
                    hot_archived = await sessions.archive_hot_sessions()
                    result["archived_hot"] += len(hot_archived)

                    # Move warm → cold
                    cold_moved = sessions.archive_warm_to_cold()
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
