"""Regression tests for executor selection (Phase 0 of the security remediation plan).

Proves the default (sandbox-disabled) path never spawns a subprocess and that
``PipelineWorkflowServices`` only wires ``SubprocessExecutor`` when the operator
has explicitly opted in via ``EXEC_SANDBOX_ENABLED``.
"""

from __future__ import annotations

import asyncio

import pytest

from reasoner.application.flows.services import PipelineWorkflowServices
from reasoner.core.settings import settings
from reasoner.infrastructure.execution.container_sandbox import ContainerExecutionSandbox
from reasoner.infrastructure.execution.noop_executor import NoopExecutor
from reasoner.infrastructure.execution.subprocess_executor import SubprocessExecutor


class _FakePipeline:
    """Minimal stand-in satisfying the attributes PipelineWorkflowServices touches."""

    router = None


def _make_services() -> PipelineWorkflowServices:
    return PipelineWorkflowServices(_FakePipeline())


def test_default_executor_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "EXEC_SANDBOX_ENABLED", False)
    services = _make_services()
    assert isinstance(services.code_executor, NoopExecutor)


def test_noop_executor_never_spawns_a_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "EXEC_SANDBOX_ENABLED", False)
    services = _make_services()

    async def _fail_if_called(*args, **kwargs):
        raise AssertionError("NoopExecutor must never create a subprocess")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fail_if_called)

    result = asyncio.run(services.code_executor.execute("print('should never run')"))
    assert result.blocked is True
    assert result.blocked_reason == "execution_disabled"
    assert result.success is False


def test_sandbox_enabled_subprocess_mode_wires_subprocess_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "EXEC_SANDBOX_ENABLED", True)
    monkeypatch.setattr(settings, "EXEC_SANDBOX_MODE", "subprocess")
    services = _make_services()
    assert isinstance(services.code_executor, SubprocessExecutor)


def test_sandbox_enabled_default_mode_wires_container_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """"container" is the default mode — the approved isolated boundary —
    so enabling the sandbox without also picking a mode must not silently
    fall back to the unisolated legacy subprocess executor."""
    monkeypatch.setattr(settings, "EXEC_SANDBOX_ENABLED", True)
    monkeypatch.setattr(settings, "EXEC_SANDBOX_MODE", "container")
    monkeypatch.setattr(settings, "SANDBOX_WORKER_URL", "http://sandbox-worker:8901")
    monkeypatch.setattr(settings, "SANDBOX_WORKER_TOKEN", "test-token")
    services = _make_services()
    assert isinstance(services.code_executor, ContainerExecutionSandbox)


class _TrackingBus:
    def __init__(self) -> None:
        self.captured: list = []

    async def publish(self, event):
        self.captured.append(event)


async def test_code_execution_completed_audit_event_reaches_the_bus() -> None:
    """CODE_EXECUTION_COMPLETED must actually publish, not just be attempted.

    Regression: ``PipelineEventType.CODE_EXECUTED`` used to map to the bare
    ``DomainEvent`` base class, which doesn't accept ``phase_name``/``exit_code``/
    etc. as constructor kwargs. ``make_event()`` raised ``TypeError`` on every
    call, and ``EventEmissionService.emit()`` swallows all exceptions
    (fire-and-forget), so the audit trail silently never wrote — with no
    error surfaced anywhere. This proves the emitted event actually reaches
    the bus with the fields the audit trail depends on.
    """
    from reasoner.application.services.event_emission_service import EventEmissionService
    from reasoner.core.events.domain_events import CodeExecutionCompleted

    bus = _TrackingBus()
    emitter = EventEmissionService(bus=bus, aggregate_id="run-audit")
    emitter.emit(
        "CODE_EXECUTION_COMPLETED",
        phase_name="pot_execute",
        exit_code=1,
        success=False,
        duration_ms=42,
        policy_version="container-v1",
    )
    await asyncio.sleep(0)  # let the fire-and-forget publish task run

    assert len(bus.captured) == 1
    event = bus.captured[0]
    assert isinstance(event, CodeExecutionCompleted)
    assert event.exit_code == 1
    assert event.policy_version == "container-v1"
    assert event.is_critical is True


async def test_code_execution_rejected_audit_event_reaches_the_bus() -> None:
    """CODE_EXECUTION_REJECTED must publish for blocked/disabled attempts too."""
    from reasoner.application.services.event_emission_service import EventEmissionService
    from reasoner.core.events.domain_events import CodeExecutionRejected

    bus = _TrackingBus()
    emitter = EventEmissionService(bus=bus, aggregate_id="run-audit")
    emitter.emit(
        "CODE_EXECUTION_REJECTED",
        phase_name="pot_execute",
        blocked_reason="execution_disabled",
    )
    await asyncio.sleep(0)

    assert len(bus.captured) == 1
    event = bus.captured[0]
    assert isinstance(event, CodeExecutionRejected)
    assert event.blocked_reason == "execution_disabled"
    assert event.is_critical is True
