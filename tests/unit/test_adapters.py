import httpx
import pytest

from app.adapters import (
    ActionUnavailable,
    CloudRunActionExecutor,
    EvidenceUnavailable,
    LiveGrafanaMCPAdapter,
    LocalActionExecutor,
    LocalGrafanaAdapter,
)
from app.domain import EvidenceMode, utcnow


@pytest.mark.asyncio
async def test_local_evidence_before_and_after():
    adapter = LocalGrafanaAdapter()
    before = await adapter.collect("run-1", False)
    after = await adapter.collect("run-1", True)
    assert [item.kind for item in before] == ["alert", "metric", "log", "trace"]
    assert before[1].values["throughput"] == 120
    assert before[2].values["oom"] is True
    assert after[1].values["throughput"] == 320
    assert after[2].values["oom"] is False
    assert all(item.source_mode == EvidenceMode.LOCAL for item in before + after)


@pytest.mark.asyncio
async def test_local_evidence_fault_modes():
    item = (
        await LocalGrafanaAdapter(stale=True, wrong_run=True, oom_after=True).collect(
            "run", True
        )
    )[0]
    assert item.run_id == "wrong-run"
    assert item.observed_at < utcnow()


@pytest.mark.asyncio
async def test_local_action_success_and_failure():
    result = await LocalActionExecutor().execute(
        run_id="run", approval_id="approval", idempotency_key="12345678"
    )
    assert result["transition"]["concurrency_after"] == 1
    with pytest.raises(ActionUnavailable, match="LOCAL_ACTION_FAILED"):
        await LocalActionExecutor(fail=True).execute(
            run_id="run", approval_id="approval", idempotency_key="12345678"
        )


@pytest.mark.asyncio
async def test_live_adapters_require_configuration(monkeypatch):
    monkeypatch.delenv("GRAFANA_MCP_URL", raising=False)
    with pytest.raises(EvidenceUnavailable, match="NOT_CONFIGURED"):
        await LiveGrafanaMCPAdapter().collect("run", False)
    monkeypatch.delenv("CUTLINE_ACTION_URL", raising=False)
    with pytest.raises(ActionUnavailable, match="NOT_CONFIGURED"):
        await CloudRunActionExecutor().execute(
            run_id="run", approval_id="approval", idempotency_key="12345678"
        )


class FakeResponse:
    def __init__(self, data, *, error=False):
        self.data = data
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise httpx.HTTPStatusError("bad", request=None, response=None)

    def json(self):
        if isinstance(self.data, Exception):
            raise self.data
        return self.data


class FakeClient:
    response = FakeResponse({})

    def __init__(self, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, *_args, **_kwargs):
        return self.response


@pytest.mark.asyncio
async def test_live_adapters_parse_success(monkeypatch):
    async def fake_call(_self, name, _arguments):
        return {
            "id": f"e-{name}",
            "summary": "ok",
            "observed_at": utcnow().isoformat(),
            "run_id": "run",
            "values": {"throughput": 320},
        }

    monkeypatch.setattr(LiveGrafanaMCPAdapter, "_call_tool", fake_call)
    evidence = await LiveGrafanaMCPAdapter("https://mcp", "token").collect("run", True)
    assert [item.kind for item in evidence] == ["alert", "metric", "log", "trace"]
    assert all(item.source_mode == EvidenceMode.LIVE for item in evidence)
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    FakeClient.response = FakeResponse({"executor_mode": "CLOUD_RUN", "transition": {}})
    result = await CloudRunActionExecutor("https://action", "token").execute(
        run_id="run", approval_id="approval", idempotency_key="12345678"
    )
    assert result["executor_mode"] == "CLOUD_RUN"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response,adapter,error",
    [
        (FakeResponse({}, error=True), "grafana", "REQUEST_FAILED"),
        (FakeResponse({"wrong": []}), "grafana", "MALFORMED"),
        (FakeResponse(ValueError("json")), "action", "ACTION_FAILED"),
    ],
)
async def test_live_adapter_failures(monkeypatch, response, adapter, error):
    if adapter == "grafana":

        async def failed_call(_self, _name, _arguments):
            if error == "MALFORMED":
                raise EvidenceUnavailable("GRAFANA_MCP_MALFORMED_RESPONSE")
            raise ValueError("invalid MCP payload")

        monkeypatch.setattr(LiveGrafanaMCPAdapter, "_call_tool", failed_call)
        with pytest.raises(EvidenceUnavailable, match=error):
            await LiveGrafanaMCPAdapter("https://mcp", "token").collect("run", False)
    else:
        monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
        FakeClient.response = response
        with pytest.raises(ActionUnavailable, match=error):
            await CloudRunActionExecutor("https://action", "token").execute(
                run_id="run", approval_id="approval", idempotency_key="12345678"
            )
