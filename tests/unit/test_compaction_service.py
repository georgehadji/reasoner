"""Unit tests for CompactionService."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from reasoner.application.services.compaction_service import CompactionService


@pytest.mark.asyncio
async def test_compaction_disabled_flag():
    """CompactionService must short-circuit when COMPACTION_ENABLED is False."""
    mock_store = AsyncMock()
    mock_store.prune_audit_events_before.return_value = 0
    service = CompactionService(mock_store)

    with patch("reasoner.application.services.compaction_service.settings") as mock_settings:
        mock_settings.COMPACTION_ENABLED = False
        mock_settings.EVENT_RETENTION_DAYS = 365
        result = await service.run_once()

    mock_store.prune_events_before.assert_not_called()
    mock_store.prune_audit_events_before.assert_not_called()
    assert result["deleted_events"] == 0
    assert result["batches"] == 0


@pytest.mark.asyncio
async def test_compaction_loops_until_partial_batch():
    """Service must keep looping until a partial batch signals exhaustion."""
    mock_store = AsyncMock()
    mock_store.prune_audit_events_before.return_value = 0
    # first two batches full (500 each), third is partial (100)
    mock_store.prune_events_before.side_effect = [500, 500, 100]
    service = CompactionService(mock_store)

    with patch("reasoner.application.services.compaction_service.settings") as mock_settings:
        mock_settings.COMPACTION_ENABLED = True
        mock_settings.EVENT_RETENTION_DAYS = 365
        result = await service.run_once()

    assert result["deleted_events"] == 1100
    assert result["batches"] == 4  # one audit batch, three event batches


@pytest.mark.asyncio
async def test_compaction_stops_on_empty_batch():
    """A batch returning 0 rows must stop the loop immediately."""
    mock_store = AsyncMock()
    mock_store.prune_audit_events_before.return_value = 0
    mock_store.prune_events_before.return_value = 0
    service = CompactionService(mock_store)

    with patch("reasoner.application.services.compaction_service.settings") as mock_settings:
        mock_settings.COMPACTION_ENABLED = True
        mock_settings.EVENT_RETENTION_DAYS = 365
        result = await service.run_once()

    assert mock_store.prune_events_before.call_count == 1
    assert result["deleted_events"] == 0
    assert result["batches"] == 2


@pytest.mark.asyncio
async def test_dry_run_uses_count_eligible():
    """Dry-run mode must call count_eligible_events and not prune."""
    mock_store = AsyncMock()
    mock_store.prune_audit_events_before.return_value = 0
    mock_store.count_eligible_events.return_value = 42
    mock_store.count_eligible_audit_events.return_value = 7
    service = CompactionService(mock_store)

    with patch("reasoner.application.services.compaction_service.settings") as mock_settings:
        mock_settings.COMPACTION_ENABLED = True
        mock_settings.EVENT_RETENTION_DAYS = 365
        result = await service.run_once(dry_run=True)

    mock_store.prune_events_before.assert_not_called()
    assert result["eligible_events"] == 42
    assert result["eligible_audit_events"] == 7
    assert result.get("dry_run") is True


@pytest.mark.asyncio
async def test_compaction_continues_after_batch_error():
    """A batch exception must stop the loop without raising to the caller."""
    mock_store = AsyncMock()
    mock_store.prune_audit_events_before.return_value = 0
    mock_store.prune_events_before.side_effect = RuntimeError("db error")
    service = CompactionService(mock_store)

    with patch("reasoner.application.services.compaction_service.settings") as mock_settings:
        mock_settings.COMPACTION_ENABLED = True
        mock_settings.EVENT_RETENTION_DAYS = 365
        result = await service.run_once()

    assert result["deleted_events"] == 0
    assert result["batches"] == 1  # the audit loop's one empty batch


@pytest.mark.asyncio
async def test_audit_rows_drained_in_their_own_loop():
    """Version-0 rows are pruned by their own method, so each call's batch cap
    still means "partial batch = done" (audit-5 decision Q6)."""
    mock_store = AsyncMock()
    mock_store.prune_audit_events_before.side_effect = [500, 20]
    mock_store.prune_events_before.return_value = 0
    service = CompactionService(mock_store)

    with patch("reasoner.application.services.compaction_service.settings") as mock_settings:
        mock_settings.COMPACTION_ENABLED = True
        mock_settings.EVENT_RETENTION_DAYS = 365
        result = await service.run_once()

    assert result["deleted_audit_events"] == 520
    assert result["deleted_events"] == 0


def test_no_compaction_task_in_lifespan():
    """Compaction runs from the admin route on an external cron, not in every
    worker (audit-5 PER-19)."""
    from pathlib import Path

    import reasoner.api as api

    source = Path(api.__file__).read_text(encoding="utf-8")
    assert "compaction" not in source.lower()
