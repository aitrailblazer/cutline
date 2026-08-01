"""CUTLINE workflow service and invariant enforcement."""

from __future__ import annotations

from datetime import timedelta
from threading import RLock
from uuid import uuid4

from app.adapters import (
    ActionExecutor,
    ActionUnavailable,
    EvidenceUnavailable,
    GrafanaAdapter,
    TelemetryPublisher,
)
from app.domain import (
    Decision,
    Diagnosis,
    Receipt,
    RecoveryProposal,
    Scenario,
    Verification,
    WorkflowState,
    calculate_impact,
    seed_shots,
    utcnow,
)


class WorkflowError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class CutlineService:
    def __init__(
        self,
        evidence: GrafanaAdapter,
        executor: ActionExecutor,
        telemetry: TelemetryPublisher | None = None,
    ) -> None:
        self.evidence_adapter = evidence
        self.executor = executor
        self.telemetry = telemetry
        self._lock = RLock()
        self._current = self._new_scenario()
        self._history: list[Scenario] = []
        self._receipts: dict[str, Receipt] = {}

    def _new_scenario(self) -> Scenario:
        run_id = str(uuid4())
        return Scenario(
            run_id=run_id,
            created_at=utcnow(),
            state=WorkflowState.READY,
            mode=self.evidence_adapter.mode,
            shots=seed_shots(),
            impact=calculate_impact(4800, 24, 120),
        )

    def get(self) -> Scenario:
        with self._lock:
            return self._current.model_copy(deep=True)

    def reset(self) -> Scenario:
        with self._lock:
            archived = self._current.model_copy(deep=True)
            archived.prior_run = True
            self._history.append(archived)
            self._current = self._new_scenario()
            return self.get()

    async def investigate(self) -> Scenario:
        with self._lock:
            if self._current.state not in {
                WorkflowState.READY,
                WorkflowState.BLOCKED,
            }:
                raise WorkflowError(
                    "INVALID_STATE", "Reset before starting another investigation."
                )
            run_id = self._current.run_id
        try:
            if self.telemetry:
                await self.telemetry.publish(run_id, False)
            evidence = await self.evidence_adapter.collect(run_id, False)
        except EvidenceUnavailable as exc:
            with self._lock:
                self._current.state = WorkflowState.BLOCKED
                self._current.blockers = [str(exc)]
            raise WorkflowError(
                "LIVE_EVIDENCE_UNAVAILABLE",
                "Live Grafana MCP evidence is unavailable; no diagnosis was created.",
                503,
            ) from exc
        if any(item.run_id != run_id for item in evidence):
            raise WorkflowError(
                "EVIDENCE_RUN_MISMATCH", "Evidence does not belong to the active run."
            )
        ids = [item.id for item in evidence]
        with self._lock:
            self._current.evidence = evidence
            self._current.diagnosis = Diagnosis(
                hypothesis=(
                    "RC3 concurrency increase caused aggregate VRAM saturation "
                    "and a multi-shot CUDA OOM retry storm."
                ),
                alternative=(
                    "A specific SQ-42 texture asset increased per-shot memory pressure."
                ),
                discriminator=(
                    "Failures span multiple shots and begin after concurrency changed 1→3."
                ),
                falsifier=(
                    "OOM continues at the same rate after rollback to concurrency 1."
                ),
                evidence_ids=ids,
            )
            self._current.proposal = RecoveryProposal(
                id=f"proposal-{run_id[:8]}", evidence_ids=ids
            )
            self._current.state = WorkflowState.AWAITING_APPROVAL
            self._current.blockers = []
            return self.get()

    def decide(
        self, *, approve: bool, approver: str, reason: str | None = None
    ) -> Scenario:
        with self._lock:
            if (
                self._current.state != WorkflowState.AWAITING_APPROVAL
                or self._current.proposal is None
            ):
                raise WorkflowError(
                    "INVALID_STATE", "A current recovery proposal is required."
                )
            now = utcnow()
            self._current.decision = Decision(
                id=f"decision-{uuid4().hex[:12]}",
                proposal_id=self._current.proposal.id,
                run_id=self._current.run_id,
                approver=approver,
                decided_at=now,
                expires_at=now + timedelta(minutes=10) if approve else None,
                status="APPROVED" if approve else "REJECTED",
                reason=reason,
            )
            if not approve:
                self._current.state = WorkflowState.REJECTED
            return self.get()

    def record_agent_synthesis(self, run_id: str, synthesis: str) -> Scenario:
        with self._lock:
            if self._current.run_id != run_id:
                raise WorkflowError(
                    "AGENT_RUN_MISMATCH", "Agent synthesis belongs to another run."
                )
            if self._current.state != WorkflowState.AWAITING_APPROVAL:
                raise WorkflowError(
                    "INVALID_STATE", "An investigated proposal is required."
                )
            self._current.agent_synthesis = synthesis
            self._current.agent_model = "gemini-2.5-flash"
            return self.get()

    def block_agent_synthesis(self, run_id: str, reason: str) -> None:
        with self._lock:
            if self._current.run_id != run_id:
                return
            self._current.state = WorkflowState.BLOCKED
            self._current.blockers = [reason]
            self._current.proposal = None

    async def execute(self, idempotency_key: str) -> Scenario:
        with self._lock:
            decision = self._current.decision
            if decision is None or decision.status != "APPROVED":
                raise WorkflowError(
                    "APPROVAL_REQUIRED", "A current approval is required."
                )
            if decision.expires_at is None or decision.expires_at <= utcnow():
                raise WorkflowError("APPROVAL_EXPIRED", "The approval has expired.")
            if decision.run_id != self._current.run_id:
                raise WorkflowError(
                    "APPROVAL_RUN_MISMATCH", "Approval belongs to another run."
                )
            if idempotency_key in self._receipts:
                self._current.receipt = self._receipts[idempotency_key]
                return self.get()
            run_id, approval_id = self._current.run_id, decision.id
        requested = utcnow()
        try:
            result = await self.executor.execute(
                run_id=run_id,
                approval_id=approval_id,
                idempotency_key=idempotency_key,
            )
        except ActionUnavailable as exc:
            receipt = Receipt(
                id=f"action-{uuid4().hex[:12]}",
                approval_id=approval_id,
                run_id=run_id,
                idempotency_key=idempotency_key,
                executor_mode="FAILED",
                status="FAILED",
                requested_at=requested,
                completed_at=utcnow(),
                transition={},
                error_code=str(exc),
            )
            with self._lock:
                self._receipts[idempotency_key] = receipt
                self._current.receipt = receipt
                self._current.state = WorkflowState.FAILED
            raise WorkflowError(
                "ACTION_FAILED",
                "The approved recovery failed and was not verified.",
                502,
            ) from exc
        receipt = Receipt(
            id=f"action-{uuid4().hex[:12]}",
            approval_id=approval_id,
            run_id=run_id,
            idempotency_key=idempotency_key,
            executor_mode=str(result["executor_mode"]),
            status="COMPLETED",
            requested_at=requested,
            completed_at=utcnow(),
            transition=dict(result["transition"]),
            annotation_id=result.get("annotation_id"),
        )
        with self._lock:
            self._receipts[idempotency_key] = receipt
            self._current.receipt = receipt
            self._current.state = WorkflowState.VERIFYING
            return self.get()

    async def verify(self) -> Scenario:
        with self._lock:
            receipt = self._current.receipt
            if receipt is None or receipt.status != "COMPLETED":
                raise WorkflowError(
                    "EXECUTION_REQUIRED", "A completed execution receipt is required."
                )
            run_id = self._current.run_id
        try:
            if self.telemetry:
                await self.telemetry.publish(run_id, True)
            evidence = await self.evidence_adapter.collect(run_id, True)
        except EvidenceUnavailable as exc:
            with self._lock:
                self._current.state = WorkflowState.BLOCKED
                self._current.blockers = [str(exc)]
            raise WorkflowError(
                "VERIFICATION_EVIDENCE_UNAVAILABLE",
                "Recovery executed, but fresh verification evidence is unavailable.",
                503,
            ) from exc
        metric = next((x for x in evidence if x.kind == "metric"), None)
        log = next((x for x in evidence if x.kind == "log"), None)
        throughput = int(metric.values.get("throughput", 0)) if metric else 0
        impact = (
            calculate_impact(4800, 24, throughput)
            if throughput > 0
            else calculate_impact(4800, 24, 1)
        )
        gates = {
            "active_run": all(x.run_id == run_id for x in evidence),
            "fresh_after_execution": all(
                x.observed_at > receipt.completed_at for x in evidence
            ),
            "safe_throughput": throughput >= impact.safe_target,
            "oom_declining": bool(log) and not bool(log.values.get("oom", True)),
            "configuration_confirmed": receipt.transition
            == {
                "concurrency_before": 3,
                "concurrency_after": 1,
                "reserve_workers_before": 0,
                "reserve_workers_after": 4,
            },
            "ahead_of_deadline": impact.variance_minutes > 0,
        }
        passed = all(gates.values())
        reasons = [name for name, value in gates.items() if not value]
        verification = Verification(
            id=f"verification-{uuid4().hex[:12]}",
            run_id=run_id,
            verified_at=utcnow(),
            passed=passed,
            gates=gates,
            impact=impact,
            evidence_ids=[item.id for item in evidence],
            reasons=reasons,
        )
        with self._lock:
            self._current.evidence.extend(evidence)
            self._current.verification = verification
            self._current.impact = impact
            self._current.state = (
                WorkflowState.VERIFIED if passed else WorkflowState.UNVERIFIED
            )
            if passed:
                self._current.shots = seed_shots(0)
            return self.get()

    def audit(self) -> dict[str, object]:
        with self._lock:
            current = self.get()
            return {
                "current": current,
                "prior_runs": [item.model_copy(deep=True) for item in self._history],
                "lineage": {
                    "run_id": current.run_id,
                    "evidence_ids": [item.id for item in current.evidence],
                    "proposal_id": current.proposal.id if current.proposal else None,
                    "decision_id": current.decision.id if current.decision else None,
                    "action_id": current.receipt.id if current.receipt else None,
                    "verification_id": (
                        current.verification.id if current.verification else None
                    ),
                },
            }
