"""PromotionService — governed promotion of harness mutations (#4b).

Only regression-free wins are promoted. cost/safety-tier mutations
require HITL approval. Each promotion writes an auditable patch artifact.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from reasoner.domain.harness_metrics import (
    HarnessMutation,
    PromotionRecord,
    ReplayResult,
)
from reasoner.application.services.regression_gate import RegressionGate, GateVerdict


class PromotionService:
    """Governed promotion of harness mutations.

    After a mutation passes the regression gate, this service:
    - Writes an auditable JSON patch to audit/harness_mutations/
    - Enforces HITL for cost/safety-tier mutations
    - Records the promotion event
    """

    def __init__(self, audit_dir: str | None = None) -> None:
        self._audit_dir = audit_dir or "audit/harness_mutations"
        self._gate = RegressionGate()

    async def attempt_promotion(
        self,
        mutation: HarnessMutation,
        result: ReplayResult,
        approver: str = "auto",
    ) -> PromotionRecord:
        """Attempt to promote a mutation after evaluation.

        Args:
            mutation: The original HarnessMutation.
            result: ReplayResult from evaluation.
            approver: "auto" for safe-tier auto-promotion,
                      "user:<name>" for HITL-approved mutations.

        Returns:
            PromotionRecord with status and artifact path.
        """
        # 1. Run regression gate
        verdict = self._gate.check(result)

        if not verdict.passed:
            return PromotionRecord(
                mutation=mutation,
                result=result,
                promoted_at=datetime.now(timezone.utc).isoformat(),
                promoted_by=approver,
                artifact_path="",
                status=f"rejected: {verdict.summary}",
            )

        # 2. Check HITL requirement for cost/safety tiers
        if mutation.risk_tier in ("cost", "safety") and approver == "auto":
            return PromotionRecord(
                mutation=mutation,
                result=result,
                promoted_at=datetime.now(timezone.utc).isoformat(),
                promoted_by="auto",
                artifact_path="",
                status="requires_human_approval",
            )

        # 3. Write auditable patch
        artifact = self._write_patch_artifact(mutation, result)

        # 4. Emit promotion event
        try:
            from reasoner.core.events.domain_events import make_event, PipelineEventType
            ev = make_event(
                PipelineEventType.HARNESS_MUTATION_PROMOTED,
                aggregate_id=f"mutation_{mutation.target}",
                version=1,
                mutation=mutation.to_dict(),
                result=result.to_dict(),
                approver=approver,
            )
            from reasoner.application.event_bus.bus import get_event_bus
            bus = get_event_bus()
            await bus.publish(ev)
        except Exception:
            pass  # event bus failure must not block promotion

        return PromotionRecord(
            mutation=mutation,
            result=result,
            promoted_at=datetime.now(timezone.utc).isoformat(),
            promoted_by=approver,
            artifact_path=str(artifact),
            status="promoted",
        )

    def _write_patch_artifact(
        self,
        mutation: HarnessMutation,
        result: ReplayResult,
    ) -> Path:
        """Write an auditable JSON patch artifact to disk."""
        audit_dir = Path(self._audit_dir)
        audit_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_target = mutation.target.replace(":", "_").replace(".", "_")
        filename = f"{timestamp}_{safe_target}_{mutation.risk_tier}.json"
        artifact_path = audit_dir / filename

        artifact = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mutation": mutation.to_dict(),
            "result": result.to_dict(),
            "rollback": mutation.rollback,
        }

        artifact_path.write_text(json.dumps(artifact, indent=2))
        return artifact_path
