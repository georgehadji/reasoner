"""Unit tests for CompactionService."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from reasoner.application.services.compaction_service import CompactionService


@pytest.mark.asyncio
async def test_compaction_disabled_flag():
    """CompactionService must short-circuit when COMPACTION_ENABLED is False."""
    mock_store = AsyncMock()
    service = CompactionService(mock_store)

    with patch("reasoner.application.services.compaction_service.settings") as mock_settings:
        mock_settings.COMPACTION_ENABLED = False
        mock_settings.EVENT_RETENTION_DAYS = 365
        result = await service.run_once()

    mock_store.prune_events_before.assert_not_called()
    assert result["deleted_events"] == 0
    assert result["batches"] == 0


@pytest.mark.asyncio
async def test_compaction_loops_until_partial_batch():
    """Service must keep looping until a partial batch signals exhaustion."""
    mock_store = AsyncMock()
    # first two batches full (500 each), third is partial (100)
    mock_store.prune_events_before.side_effect = [500, 500, 100]
    service = CompactionService(mock_store)

    with patch("reasoner.application.services.compaction_service.settings") as mock_settings:
        mock_settings.COMPACTION_ENABLED = True
        mock_settings.EVENT_RETENTION_DAYS = 365
        result = await service.run_once()

    assert result["deleted_events"] == 1100
    assert result["batches"] == 3


@pytest.mark.asyncio
async def test_compaction_stops_on_empty_batch():
    """A batch returning 0 rows must stop the loop immediately."""
    mock_store = AsyncMock()
    mock_store.prune_events_before.return_value = 0
    service = CompactionService(mock_store)

    with patch("reasoner.application.services.compaction_service.settings") as mock_settings:
        mock_settings.COMPACTION_ENABLED = True
        mock_settings.EVENT_RETENTION_DAYS = 365
        result = await service.run_once()

    assert mock_store.prune_events_before.call_count == 1
    assert result["deleted_events"] == 0
    assert result["batches"] == 1


@pytest.mark.asyncio
async def test_dry_run_uses_count_eligible():
    """Dry-run mode must call count_eligible_events and not prune."""
    mock_store = AsyncMock()
    mock_store.count_eligible_events.return_value = 42
    service = CompactionService(mock_store)

    with patch("reasoner.application.services.compaction_service.settings") as mock_settings:
        mock_settings.COMPACTION_ENABLED = True
        mock_settings.EVENT_RETENTION_DAYS = 365
        result = await service.run_once(dry_run=True)

    mock_store.prune_events_before.assert_not_called()
    assert result["eligible_events"] == 42
    assert result.get("dry_run") is True


@pytest.mark.asyncio
async def test_compaction_continues_after_batch_error():
    """A batch exception must stop the loop without raising to the caller."""
    mock_store = AsyncMock()
    mock_store.prune_events_before.side_effect = RuntimeError("db error")
    service = CompactionService(mock_store)

    with patch("reasoner.application.services.compaction_service.settings") as mock_settings:
        mock_settings.COMPACTION_ENABLED = True
        mock_settings.EVENT_RETENTION_DAYS = 365
        result = await service.run_once()

    assert result["deleted_events"] == 0
    assert result["batches"] == 0
