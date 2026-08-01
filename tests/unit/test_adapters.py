from types import SimpleNamespace

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
    timestamp = utcnow().timestamp()

    async def fake_session_call(_self, _name, _arguments=None):
        return SimpleNamespace(
            tools=[
                SimpleNamespace(name="list_datasources"),
                SimpleNamespace(name="query_prometheus"),
                SimpleNamespace(name="query_loki_logs"),
            ]
        )

    async def fake_call(_self, name, _arguments):
        if name == "list_datasources":
            return {
                "datasources": [
                    {"uid": "prom", "type": "prometheus"},
                    {"uid": "loki", "type": "loki"},
                ]
            }
        if name == "query_prometheus":
            return {
                "data": {
                    "resultType": "vector",
                    "result": [
                        {
                            "metric": {
                                "__name__": "cutline_release_backlog_frames",
                                "run_id": "run-12345678",
                            },
                            "value": [timestamp, "4800"],
                        },
                        {
                            "metric": {
                                "__name__": "cutline_render_throughput_fpm",
                                "run_id": "run-12345678",
                            },
                            "value": [timestamp, "320"],
                        },
                    ],
                }
            }
        return {
            "data": [
                {
                    "timestamp": str(int(timestamp * 1_000_000_000)),
                    "line": '{"oom":false,"event":"render_status"}',
                    "labels": {"run_id": "run-12345678"},
                }
            ]
        }

    monkeypatch.setattr(LiveGrafanaMCPAdapter, "_session_call", fake_session_call)
    monkeypatch.setattr(LiveGrafanaMCPAdapter, "_call_tool", fake_call)
    evidence = await LiveGrafanaMCPAdapter("https://mcp", "token").collect(
        "run-12345678", True
    )
    assert [item.kind for item in evidence] == ["metric", "log"]
    assert evidence[0].values == {"backlog_frames": 4800, "throughput": 320}
    assert evidence[1].values["oom"] is False
    assert all(item.source_mode == EvidenceMode.LIVE for item in evidence)
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    FakeClient.response = FakeResponse({"executor_mode": "CLOUD_RUN", "transition": {}})
    result = await CloudRunActionExecutor("https://action", "token").execute(
        run_id="run", approval_id="approval", idempotency_key="12345678"
    )
    assert result["executor_mode"] == "CLOUD_RUN"


@pytest.mark.asyncio
async def test_live_grafana_auth_tool_and_datasource_guards(monkeypatch):
    token_adapter = LiveGrafanaMCPAdapter("https://mcp", "token")
    assert await token_adapter._headers() == {"Authorization": "Bearer token"}

    identity_adapter = LiveGrafanaMCPAdapter("https://mcp")
    identity_adapter.use_google_identity = True
    monkeypatch.setattr("app.adapters.fetch_id_token", lambda *_args: "id-token")
    assert await identity_adapter._headers() == {"Authorization": "Bearer id-token"}
    identity_adapter.use_google_identity = False
    assert await identity_adapter._headers() == {}

    async def missing_tools(_name, _arguments=None):
        return SimpleNamespace(tools=[SimpleNamespace(name="list_datasources")])

    identity_adapter._session_call = missing_tools
    with pytest.raises(EvidenceUnavailable, match="REQUIRED_TOOLS_MISSING"):
        await identity_adapter._verify_tools()
    identity_adapter._tools_verified = True
    await identity_adapter._verify_tools()

    identity_adapter._datasources = {"prometheus": "p", "loki": "l"}
    await identity_adapter._discover_datasources()
    identity_adapter._datasources = {}

    async def malformed_datasources(_name, _arguments):
        return {"datasources": "wrong"}

    identity_adapter._call_tool = malformed_datasources
    with pytest.raises(EvidenceUnavailable, match="DATASOURCES_MALFORMED"):
        await identity_adapter._discover_datasources()

    async def missing_datasources(_name, _arguments):
        return {
            "datasources": [
                "skip",
                {"uid": "other", "type": "tempo"},
                {"uid": "", "type": "loki"},
            ]
        }

    identity_adapter._call_tool = missing_datasources
    with pytest.raises(EvidenceUnavailable, match="DATASOURCES_MISSING"):
        await identity_adapter._discover_datasources()


def test_live_grafana_provider_evidence_guards():
    timestamp = utcnow().timestamp()
    with pytest.raises(EvidenceUnavailable, match="TIMESTAMP_MISSING"):
        LiveGrafanaMCPAdapter._timestamp("not-time")
    assert (
        LiveGrafanaMCPAdapter._timestamp(int(timestamp * 1_000_000_000)).tzinfo
        is not None
    )

    with pytest.raises(EvidenceUnavailable, match="METRIC_EVIDENCE_MISSING"):
        LiveGrafanaMCPAdapter._metric_evidence({}, "run", "pre")
    invalid_series = {
        "data": {
            "result": [
                "skip",
                {"metric": "wrong", "value": []},
                {
                    "metric": {"__name__": "unknown"},
                    "value": [timestamp, "1"],
                },
            ]
        }
    }
    with pytest.raises(EvidenceUnavailable, match="METRIC_PROVENANCE_INVALID"):
        LiveGrafanaMCPAdapter._metric_evidence(invalid_series, "run-12345678", "pre")

    for payload, error in [
        ({}, "LOG_EVIDENCE_MISSING"),
        ({"data": ["wrong"]}, "LOG_EVIDENCE_MALFORMED"),
        (
            {
                "data": [
                    {
                        "timestamp": timestamp,
                        "line": "{}",
                        "labels": {"run_id": "wrong"},
                    }
                ]
            },
            "LOG_PROVENANCE_INVALID",
        ),
        (
            {
                "data": [
                    {
                        "timestamp": timestamp,
                        "line": "not-json",
                        "labels": {"run_id": "run"},
                    }
                ]
            },
            "LOG_EVIDENCE_MALFORMED",
        ),
        (
            {
                "data": [
                    {
                        "timestamp": timestamp,
                        "line": '{"oom":"yes"}',
                        "labels": {"run_id": "run"},
                    }
                ]
            },
            "LOG_EVIDENCE_MALFORMED",
        ),
    ]:
        with pytest.raises(EvidenceUnavailable, match=error):
            LiveGrafanaMCPAdapter._log_evidence(payload, "run", "pre")


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

        async def tools_ok(_self, _name, _arguments=None):
            return SimpleNamespace(
                tools=[
                    SimpleNamespace(name="list_datasources"),
                    SimpleNamespace(name="query_prometheus"),
                    SimpleNamespace(name="query_loki_logs"),
                ]
            )

        monkeypatch.setattr(LiveGrafanaMCPAdapter, "_session_call", tools_ok)
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
