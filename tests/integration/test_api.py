from fastapi.testclient import TestClient

from app.adapters import CloudRunActionExecutor, LiveGrafanaMCPAdapter
from app.api import create_app, service_from_environment
from app.domain import EvidenceMode


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
    client = TestClient(create_app(service))
    readiness = client.get("/api/readiness").json()
    assert readiness["ready"] is False
    assert "LIVE_RUNTIME_CONFIGURATION_INCOMPLETE" in readiness["blockers"]
    monkeypatch.setenv("GRAFANA_MCP_URL", "https://example")
    monkeypatch.setenv("GRAFANA_MCP_TOKEN", "secret")
    monkeypatch.setenv("CUTLINE_ACTION_URL", "https://action")
    ready = (
        TestClient(create_app(service_from_environment())).get("/api/readiness").json()
    )
    assert ready["ready"] is True
    monkeypatch.setenv("CUTLINE_MODE", "local")
    assert service_from_environment().get().mode == EvidenceMode.LOCAL


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
