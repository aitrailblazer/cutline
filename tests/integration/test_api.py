from typing import Any

from fastapi.testclient import TestClient

from app.actions import MemoryActionRecordStore
from app.adapters import (
    CloudRunActionExecutor,
    LiveGrafanaMCPAdapter,
    LiveGrafanaTelemetryPublisher,
    LocalActionExecutor,
    LocalGrafanaAdapter,
)
from app.agent_runtime import AgentSynthesisUnavailable, HostedInvestigator
from app.api import create_app, service_from_environment
from app.domain import EvidenceMode
from app.service import CutlineService


class FakeLiveGrafanaAdapter(LocalGrafanaAdapter):
    mode = EvidenceMode.LIVE


class FakeHostedInvestigator(HostedInvestigator):
    def __init__(self, fail=False):
        self.fail = fail
        self.run_ids = []

    async def synthesize(self, run_id):
        self.run_ids.append(run_id)
        if self.fail:
            raise AgentSynthesisUnavailable("ADK_AGENT_REQUEST_FAILED")
        return "Observed evidence pre-1; hypothesis retained with alternative."


def test_index_health_readiness_and_assets(client):
    assert client.get("/").status_code == 200
    assert "SQ-42 release command" in client.get("/").text
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/healthz").json() == {"status": "ok"}
    readiness = client.get("/api/readiness").json()
    assert readiness["ready"] is True
    assert readiness["mode"] == "LOCAL_CONTROLLED"
    assert "GRAFANA_MCP_TOKEN" not in str(readiness)
    scenario = client.get("/api/scenario").json()
    assert "deterministic local evidence and action adapters" in scenario["disclosure"]
    assert "no live provider claim" in scenario["disclosure"]


def test_api_success_journey_and_refresh(client):
    first = client.get("/api/scenario").json()
    assert len(first["shots"]) == 18
    investigated = client.post("/api/scenario/investigate").json()
    assert investigated["state"] == "AWAITING_APPROVAL"
    approved = client.post(
        "/api/scenario/approve", json={"approver": "Maya Chen"}
    ).json()
    assert approved["decision"]["status"] == "APPROVED"
    executed = client.post(
        "/api/scenario/execute", json={"idempotency_key": "api-success-key"}
    ).json()
    assert executed["state"] == "VERIFYING"
    assert (
        client.get("/api/scenario").json()["receipt"]["id"] == executed["receipt"]["id"]
    )
    verified = client.post("/api/scenario/verify").json()
    assert verified["state"] == "VERIFIED"
    audit = client.get("/api/audit").json()
    assert audit["lineage"]["action_id"] == verified["receipt"]["id"]
    reset = client.post("/api/scenario/reset").json()
    assert reset["run_id"] != first["run_id"]


def test_api_rejection_and_safe_error(client):
    client.post("/api/scenario/investigate")
    rejected = client.post(
        "/api/scenario/reject",
        json={"approver": "Maya Chen", "reason": "No"},
    ).json()
    assert rejected["state"] == "REJECTED"
    response = client.post(
        "/api/scenario/execute", json={"idempotency_key": "rejected-key"}
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "APPROVAL_REQUIRED"
    assert "Traceback" not in str(error)
    assert error["guidance"]


def test_validation_is_public_safe(client):
    response = client.post("/api/scenario/execute", json={"idempotency_key": "x"})
    assert response.status_code == 422
    assert "/Users/" not in response.text


def test_environment_service_modes(monkeypatch):
    monkeypatch.setenv("CUTLINE_MODE", "live")
    service = service_from_environment()
    assert isinstance(service.evidence_adapter, LiveGrafanaMCPAdapter)
    assert isinstance(service.executor, CloudRunActionExecutor)
    assert isinstance(service.telemetry, LiveGrafanaTelemetryPublisher)
    client = TestClient(create_app(service))
    readiness = client.get("/api/readiness").json()
    assert readiness["ready"] is False
    assert "LIVE_RUNTIME_CONFIGURATION_INCOMPLETE" in readiness["blockers"]
    monkeypatch.setenv("GRAFANA_MCP_URL", "https://example")
    monkeypatch.setenv("GRAFANA_MCP_TOKEN", "secret")
    monkeypatch.setenv("GRAFANA_PROMETHEUS_DATASOURCE_UID", "prom")
    monkeypatch.setenv("GRAFANA_LOKI_DATASOURCE_UID", "loki")
    monkeypatch.setenv("CUTLINE_ACTION_URL", "https://action")
    monkeypatch.setenv("CUTLINE_ACTION_TOKEN", "action-secret")
    monkeypatch.setenv("GRAFANA_PROMETHEUS_PUSH_URL", "https://prom/push")
    monkeypatch.setenv("GRAFANA_PROMETHEUS_USER", "prom-user")
    monkeypatch.setenv("GRAFANA_LOKI_PUSH_URL", "https://loki/push")
    monkeypatch.setenv("GRAFANA_LOKI_USER", "loki-user")
    monkeypatch.setenv("GRAFANA_TELEMETRY_TOKEN", "telemetry-secret")
    ready = (
        TestClient(create_app(service_from_environment())).get("/api/readiness").json()
    )
    assert ready["ready"] is True
    monkeypatch.setenv("CUTLINE_MODE", "local")
    assert service_from_environment().get().mode == EvidenceMode.LOCAL


def test_live_action_boundary_auth_validation_and_idempotency(client, monkeypatch):
    payload = {
        "run_id": "run-12345678",
        "approval_id": "approval-12345678",
        "idempotency_key": "action-key-12345678",
        "plan_version": "sq42-recovery-v1",
    }
    path = "/internal/actions/sq42-recovery"
    assert client.post(path, json=payload).status_code == 503
    monkeypatch.setenv("CUTLINE_ACTION_TOKEN", "action-secret")
    assert client.post(path, json=payload).status_code == 401
    headers = {"Authorization": "Bearer action-secret"}
    first = client.post(path, headers=headers, json=payload)
    assert first.status_code == 200
    assert first.json()["executor_mode"] == "CLOUD_RUN"
    assert first.json()["replayed"] is False
    replay = client.post(path, headers=headers, json=payload)
    assert replay.json()["replayed"] is True
    conflict = client.post(
        path,
        headers=headers,
        json={**payload, "approval_id": "approval-different"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "IDEMPOTENCY_KEY_REUSE"
    invalid = client.post(
        path,
        headers=headers,
        json={**payload, "plan_version": "unapproved"},
    )
    assert invalid.status_code == 422
    assert (
        "action-secret" not in first.text + replay.text + conflict.text + invalid.text
    )


def test_live_action_boundary_handler_conflict(monkeypatch, service):
    class RejectingStore(MemoryActionRecordStore):
        async def create_or_get(
            self, idempotency_key: str, fingerprint: str, record: dict[str, Any]
        ) -> tuple[dict[str, Any], bool]:
            from app.actions import ActionBoundaryError

            raise ActionBoundaryError("STORE_CONFLICT")

    monkeypatch.setenv("CUTLINE_ACTION_TOKEN", "action-secret")
    client = TestClient(create_app(service, RejectingStore()))
    response = client.post(
        "/internal/actions/sq42-recovery",
        headers={"Authorization": "Bearer action-secret"},
        json={
            "run_id": "run-12345678",
            "approval_id": "approval-12345678",
            "idempotency_key": "action-key-12345678",
            "plan_version": "sq42-recovery-v1",
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "STORE_CONFLICT"


def test_live_investigation_invokes_agent_and_records_synthesis():
    service = CutlineService(FakeLiveGrafanaAdapter(), LocalActionExecutor())
    investigator = FakeHostedInvestigator()
    client = TestClient(create_app(service, MemoryActionRecordStore(), investigator))
    response = client.post("/api/scenario/investigate")
    assert response.status_code == 200
    scenario = response.json()
    assert "official Grafana MCP runtime" in scenario["disclosure"]
    assert "Gemini 2.5 Flash" in scenario["disclosure"]
    assert "authenticated Google Cloud action" in scenario["disclosure"]
    assert investigator.run_ids == [scenario["run_id"]]
    assert scenario["agent_model"] == "gemini-2.5-flash"
    assert "pre-1" in scenario["agent_synthesis"]


def test_live_investigation_blocks_when_agent_fails():
    service = CutlineService(FakeLiveGrafanaAdapter(), LocalActionExecutor())
    client = TestClient(
        create_app(
            service,
            MemoryActionRecordStore(),
            FakeHostedInvestigator(fail=True),
        )
    )
    response = client.post("/api/scenario/investigate")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AGENT_SYNTHESIS_UNAVAILABLE"
    scenario = client.get("/api/scenario").json()
    assert scenario["state"] == "BLOCKED"
    assert scenario["proposal"] is None
    assert scenario["blockers"] == ["ADK_AGENT_REQUEST_FAILED"]


def test_five_consecutive_api_runs(client):
    run_ids = set()
    for index in range(5):
        scenario = client.post("/api/scenario/reset").json()
        run_ids.add(scenario["run_id"])
        client.post("/api/scenario/investigate")
        client.post("/api/scenario/approve", json={"approver": "Maya Chen"})
        client.post(
            "/api/scenario/execute",
            json={"idempotency_key": f"reliability-{index}"},
        )
        result = client.post("/api/scenario/verify").json()
        assert result["state"] == "VERIFIED"
        assert result["impact"]["variance_minutes"] == 9
    assert len(run_ids) == 5
