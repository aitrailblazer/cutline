"""CUTLINE deterministic domain contract."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class WorkflowState(StrEnum):
    READY = "READY"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    REJECTED = "REJECTED"
    VERIFYING = "VERIFYING"
    VERIFIED = "VERIFIED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    UNVERIFIED = "UNVERIFIED"


class EvidenceMode(StrEnum):
    LOCAL = "LOCAL_CONTROLLED"
    LIVE = "LIVE_GRAFANA_MCP"


class Shot(BaseModel):
    id: str
    frame_start: int
    frame_end: int
    remaining_frames: int
    attempts: int
    worker: str
    eta_minutes: int
    dependency: str = "Streaming package"
    at_risk: bool
    status: str


class Evidence(BaseModel):
    id: str
    kind: str
    operation: str
    summary: str
    observed_at: datetime
    run_id: str
    source_mode: EvidenceMode
    values: dict[str, Any] = Field(default_factory=dict)


class Impact(BaseModel):
    backlog_frames: int
    deadline_minutes: int
    observed_throughput: int
    deadline_minimum: int
    safe_target: int
    projected_minutes: int
    variance_minutes: int
    label: str
    formulas: list[str]


class Diagnosis(BaseModel):
    evidence_status: str = "Supported"
    hypothesis: str
    alternative: str
    discriminator: str
    falsifier: str
    evidence_ids: list[str]
    missing_evidence: list[str] = Field(default_factory=list)


class RecoveryProposal(BaseModel):
    id: str
    version: str = "sq42-recovery-v1"
    concurrency_before: int = 3
    concurrency_after: int = 1
    reserve_workers_before: int = 0
    reserve_workers_after: int = 4
    scope: str = "SQ-42 render pool only"
    scenario_cost_usd: int = 18
    rollback: str = "Restore prior worker configuration"
    stop_condition: str = "Stop if OOM rate does not decline after rollback"
    evidence_ids: list[str]


class Decision(BaseModel):
    id: str
    proposal_id: str
    run_id: str
    approver: str
    decided_at: datetime
    expires_at: datetime | None = None
    status: str
    reason: str | None = None


class Receipt(BaseModel):
    id: str
    approval_id: str
    run_id: str
    idempotency_key: str
    executor_mode: str
    status: str
    requested_at: datetime
    completed_at: datetime
    transition: dict[str, int]
    annotation_id: str | None = None
    error_code: str | None = None


class Verification(BaseModel):
    id: str
    run_id: str
    verified_at: datetime
    passed: bool
    gates: dict[str, bool]
    impact: Impact
    evidence_ids: list[str]
    reasons: list[str] = Field(default_factory=list)


class Scenario(BaseModel):
    run_id: str
    created_at: datetime
    state: WorkflowState
    mode: EvidenceMode
    production: str = "Eclipse Protocol — Episode 6"
    operator: str = "Maya Chen"
    sequence: str = "SQ-42"
    deadline_minutes: int = 24
    backlog_frames: int = 4800
    shots: list[Shot]
    evidence: list[Evidence] = Field(default_factory=list)
    diagnosis: Diagnosis | None = None
    impact: Impact
    proposal: RecoveryProposal | None = None
    decision: Decision | None = None
    receipt: Receipt | None = None
    verification: Verification | None = None
    blockers: list[str] = Field(default_factory=list)
    prior_run: bool = False
    disclosure: str = (
        "Controlled synthetic workload; local evidence adapter for development. "
        "Submitted live mode requires real Grafana MCP evidence and Google Cloud action."
    )


def utcnow() -> datetime:
    return datetime.now(UTC)


def calculate_impact(
    backlog_frames: int, deadline_minutes: int, throughput: int
) -> Impact:
    """Calculate deadline impact with reproducible integer arithmetic."""
    if backlog_frames <= 0 or deadline_minutes <= 0 or throughput <= 0:
        raise ValueError("backlog, deadline, and throughput must be positive")
    minimum = (Decimal(backlog_frames) / Decimal(deadline_minutes)).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    safe = (minimum * Decimal("1.20")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    projected = (Decimal(backlog_frames) / Decimal(throughput)).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    variance = Decimal(deadline_minutes) - projected
    variance_int = int(variance)
    label = (
        f"{abs(variance_int)} minutes early"
        if variance_int >= 0
        else f"{abs(variance_int)} minutes late"
    )
    return Impact(
        backlog_frames=backlog_frames,
        deadline_minutes=deadline_minutes,
        observed_throughput=throughput,
        deadline_minimum=int(minimum),
        safe_target=int(safe),
        projected_minutes=int(projected),
        variance_minutes=variance_int,
        label=label,
        formulas=[
            f"{backlog_frames} / {deadline_minutes} = {int(minimum)} deadline minimum",
            f"{int(minimum)} * 1.20 = {int(safe)} safe target",
            f"{backlog_frames} / {throughput} = {int(projected)} projected minutes",
            f"{deadline_minutes} - {int(projected)} = {variance_int} deadline variance",
        ],
    )


def seed_shots(at_risk_count: int = 12) -> list[Shot]:
    """Build a stable, media-native eighteen-shot manifest."""
    shots = []
    for index in range(18):
        number = index + 1
        at_risk = index < at_risk_count
        shots.append(
            Shot(
                id=f"SQ42-{number:03d}",
                frame_start=index * 300 + 1,
                frame_end=(index + 1) * 300,
                remaining_frames=400 if at_risk else 0,
                attempts=3 if at_risk else 1,
                worker=f"gpu-{(index % 4) + 1:02d}",
                eta_minutes=28 + index if at_risk else 10 + index,
                at_risk=at_risk,
                status="AT RISK" if at_risk else "READY",
            )
        )
    return shots
