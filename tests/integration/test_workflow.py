from datetime import timedelta

import pytest

from app.adapters import LocalActionExecutor, LocalGrafanaAdapter
from app.domain import WorkflowState, utcnow
from app.service import CutlineService, WorkflowError
from tests.conftest import advance_to_approval, advance_to_verification


@pytest.mark.asyncio
async def test_complete_success_and_audit(service):
    initial = service.get()
    assert initial.state == WorkflowState.READY
    investigated = await service.investigate()
    assert investigated.state == WorkflowState.AWAITING_APPROVAL
    assert len(investigated.evidence) == 4
    assert investigated.diagnosis.evidence_status == "Supported"
    assert investigated.proposal.scenario_cost_usd == 18
    approved = service.decide(approve=True, approver="Maya Chen")
    assert approved.decision.status == "APPROVED"
    executed = await service.execute("success-key")
    assert executed.state == WorkflowState.VERIFYING
    assert executed.receipt.status == "COMPLETED"
    verified = await service.verify()
    assert verified.state == WorkflowState.VERIFIED
    assert verified.verification.passed
    assert verified.impact.variance_minutes == 9
    assert not any(shot.at_risk for shot in verified.shots)
    audit = service.audit()
    assert audit["lineage"]["verification_id"] == verified.verification.id
    reset = service.reset()
    assert reset.run_id != initial.run_id
    assert service.audit()["prior_runs"][-1].prior_run


@pytest.mark.asyncio
async def test_agent_synthesis_run_and_state_guards(service):
    scenario = await service.investigate()
    recorded = service.record_agent_synthesis(scenario.run_id, "bounded synthesis")
    assert recorded.agent_synthesis == "bounded synthesis"
    assert recorded.agent_model == "gemini-2.5-flash"
    with pytest.raises(WorkflowError, match="another run"):
        service.record_agent_synthesis("wrong-run", "invalid")
    service.decide(approve=False, approver="Maya Chen")
    with pytest.raises(WorkflowError, match="investigated proposal"):
        service.record_agent_synthesis(scenario.run_id, "too late")
    service.block_agent_synthesis("wrong-run", "ignored")


@pytest.mark.asyncio
async def test_reject_and_invalid_transitions(service):
    with pytest.raises(WorkflowError, match="current recovery proposal"):
        service.decide(approve=True, approver="Maya")
    await service.investigate()
    rejected = service.decide(approve=False, approver="Maya", reason="Not now")
    assert rejected.state == WorkflowState.REJECTED
    assert rejected.receipt is None
    with pytest.raises(WorkflowError, match="Reset"):
        await service.investigate()
    with pytest.raises(WorkflowError, match="approval"):
        await service.execute("no-approval")
    with pytest.raises(WorkflowError, match="execution receipt"):
        await service.verify()


@pytest.mark.asyncio
async def test_approval_expiry_and_mismatch(service):
    await advance_to_approval(service)
    service._current.decision.expires_at = utcnow() - timedelta(seconds=1)
    with pytest.raises(WorkflowError, match="expired"):
        await service.execute("expired-key")
    service._current.decision.expires_at = utcnow() + timedelta(minutes=1)
    service._current.decision.run_id = "wrong"
    with pytest.raises(WorkflowError, match="another run"):
        await service.execute("wrong-run-key")


@pytest.mark.asyncio
async def test_idempotent_execution(service):
    await advance_to_approval(service)
    first = await service.execute("stable-key")
    second = await service.execute("stable-key")
    assert first.receipt.id == second.receipt.id
    assert len(service._receipts) == 1


@pytest.mark.asyncio
async def test_evidence_unavailable_and_wrong_run():
    class Broken(LocalGrafanaAdapter):
        async def collect(self, run_id, after_action):
            from app.adapters import EvidenceUnavailable

            raise EvidenceUnavailable("down")

    broken = CutlineService(Broken(), LocalActionExecutor())
    with pytest.raises(WorkflowError) as exc:
        await broken.investigate()
    assert exc.value.status_code == 503
    assert broken.get().state == WorkflowState.BLOCKED
    wrong = CutlineService(LocalGrafanaAdapter(wrong_run=True), LocalActionExecutor())
    with pytest.raises(WorkflowError, match="active run"):
        await wrong.investigate()


@pytest.mark.asyncio
async def test_action_failure():
    service = CutlineService(LocalGrafanaAdapter(), LocalActionExecutor(fail=True))
    await advance_to_approval(service)
    with pytest.raises(WorkflowError) as exc:
        await service.execute("failure-key")
    assert exc.value.status_code == 502
    assert service.get().state == WorkflowState.FAILED
    assert service.get().receipt.error_code == "LOCAL_ACTION_FAILED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "adapter,failed_gate",
    [
        (LocalGrafanaAdapter(throughput_after=220), "safe_throughput"),
        (LocalGrafanaAdapter(oom_after=True), "oom_declining"),
        (LocalGrafanaAdapter(stale=True), "fresh_after_execution"),
    ],
)
async def test_verification_fail_closed(adapter, failed_gate):
    service = CutlineService(adapter, LocalActionExecutor())
    await advance_to_verification(service)
    result = await service.verify()
    assert result.state == WorkflowState.UNVERIFIED
    assert not result.verification.gates[failed_gate]
    assert failed_gate in result.verification.reasons


@pytest.mark.asyncio
async def test_verification_rejects_post_action_wrong_run():
    class PostWrongRun(LocalGrafanaAdapter):
        async def collect(self, run_id, after_action):
            items = await super().collect(run_id, after_action)
            if after_action:
                for item in items:
                    item.run_id = "wrong-run"
            return items

    service = CutlineService(PostWrongRun(), LocalActionExecutor())
    await advance_to_verification(service)
    result = await service.verify()
    assert result.state == WorkflowState.UNVERIFIED
    assert not result.verification.gates["active_run"]
    assert "active_run" in result.verification.reasons


@pytest.mark.asyncio
async def test_verification_evidence_unavailable():
    class PostBroken(LocalGrafanaAdapter):
        async def collect(self, run_id, after_action):
            if after_action:
                from app.adapters import EvidenceUnavailable

                raise EvidenceUnavailable("post down")
            return await super().collect(run_id, after_action)

    service = CutlineService(PostBroken(), LocalActionExecutor())
    await advance_to_verification(service)
    with pytest.raises(WorkflowError) as exc:
        await service.verify()
    assert exc.value.status_code == 503
    assert service.get().state == WorkflowState.BLOCKED


@pytest.mark.asyncio
async def test_missing_metric_produces_unverified():
    class NoMetric(LocalGrafanaAdapter):
        async def collect(self, run_id, after_action):
            items = await super().collect(run_id, after_action)
            return [item for item in items if item.kind != "metric"]

    service = CutlineService(NoMetric(), LocalActionExecutor())
    await advance_to_verification(service)
    result = await service.verify()
    assert result.state == WorkflowState.UNVERIFIED
    assert result.impact.observed_throughput == 1
