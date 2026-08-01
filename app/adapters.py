"""Evidence and action adapters with explicit local/live boundaries."""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from asyncio import to_thread
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.id_token import fetch_id_token
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.domain import Evidence, EvidenceMode, utcnow


class EvidenceUnavailable(RuntimeError):
    pass


class ActionUnavailable(RuntimeError):
    pass


class GrafanaAdapter(ABC):
    mode: EvidenceMode

    @abstractmethod
    async def collect(self, run_id: str, after_action: bool) -> list[Evidence]:
        raise NotImplementedError


class LocalGrafanaAdapter(GrafanaAdapter):
    mode = EvidenceMode.LOCAL

    def __init__(
        self,
        *,
        throughput_after: int = 320,
        stale: bool = False,
        wrong_run: bool = False,
        oom_after: bool = False,
    ) -> None:
        self.throughput_after = throughput_after
        self.stale = stale
        self.wrong_run = wrong_run
        self.oom_after = oom_after

    async def collect(self, run_id: str, after_action: bool) -> list[Evidence]:
        observed = utcnow() - timedelta(minutes=10) if self.stale else utcnow()
        evidence_run = "wrong-run" if self.wrong_run else run_id
        throughput = self.throughput_after if after_action else 120
        oom = self.oom_after if after_action else True
        phase = "post" if after_action else "pre"
        raw = [
            (
                "alert",
                "get_alert",
                "RenderDeadlineRiskHigh is resolved"
                if after_action and not oom
                else "RenderDeadlineRiskHigh is active",
                {"active": not after_action or oom},
            ),
            (
                "metric",
                "query_prometheus",
                f"Backlog 4800; throughput {throughput} frames/min",
                {
                    "backlog_frames": 4800,
                    "throughput": throughput,
                    "gpu_memory_ratio": 0.62 if after_action else 0.98,
                    "retry_rate": 0 if after_action and not oom else 12,
                },
            ),
            (
                "log",
                "query_loki_logs",
                "CUDA OOM persists" if oom else "No new CUDA OOM events",
                {"oom": oom, "release": "2026.07.31-rc3"},
            ),
            (
                "trace",
                "query_tempo_trace",
                "render_shot → texture_load",
                {"operation": "render_shot", "child": "texture_load"},
            ),
        ]
        return [
            Evidence(
                id=f"{phase}-{index}-{run_id[:8]}",
                kind=kind,
                operation=operation,
                summary=summary,
                observed_at=observed,
                run_id=evidence_run,
                source_mode=self.mode,
                values=values,
            )
            for index, (kind, operation, summary, values) in enumerate(raw, 1)
        ]


class LiveGrafanaMCPAdapter(GrafanaAdapter):
    """Fail-closed, protocol-native client for a hosted Grafana MCP server."""

    mode = EvidenceMode.LIVE

    def __init__(self, url: str | None = None, token: str | None = None) -> None:
        self.url = url or os.getenv("GRAFANA_MCP_URL")
        self.token = token or os.getenv("GRAFANA_MCP_TOKEN")
        self.use_google_identity = (
            os.getenv("GRAFANA_MCP_USE_GOOGLE_ID_TOKEN", "").lower() == "true"
        )
        self.audience = os.getenv("GRAFANA_MCP_AUDIENCE") or self.url
        self._datasources: dict[str, str] = {}
        self._tools_verified = False

    async def _headers(self) -> dict[str, str]:
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        if self.use_google_identity and self.audience:
            token = await to_thread(fetch_id_token, GoogleAuthRequest(), self.audience)
            return {"Authorization": f"Bearer {token}"}
        return {}

    async def _session_call(  # pragma: no cover - live MCP transport boundary
        self, name: str | None, arguments: dict[str, Any] | None = None
    ) -> Any:
        headers = await self._headers()
        async with httpx.AsyncClient(headers=headers, timeout=20) as client:
            async with streamable_http_client(self.url, http_client=client) as streams:
                read_stream, write_stream, _ = streams
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    if name is None:
                        return await session.list_tools()
                    return await session.call_tool(name, arguments or {})

    async def _call_tool(  # pragma: no cover - exercised only against a live MCP server
        self, name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        result = await self._session_call(name, arguments)
        if result.isError:
            raise EvidenceUnavailable("GRAFANA_MCP_TOOL_FAILED")
        if result.structuredContent:
            return dict(result.structuredContent)
        text = next(
            (
                item.text
                for item in result.content
                if getattr(item, "type", None) == "text"
            ),
            None,
        )
        if not text:
            raise EvidenceUnavailable("GRAFANA_MCP_EMPTY_RESPONSE")
        try:
            payload = json.loads(text)
        except ValueError as exc:
            raise EvidenceUnavailable("GRAFANA_MCP_MALFORMED_RESPONSE") from exc
        if not isinstance(payload, dict):
            raise EvidenceUnavailable("GRAFANA_MCP_MALFORMED_RESPONSE")
        return payload

    async def _verify_tools(self) -> None:
        if self._tools_verified:
            return
        result = await self._session_call(None)
        names = {tool.name for tool in result.tools}
        required = {"list_datasources", "query_prometheus", "query_loki_logs"}
        if not required.issubset(names):
            raise EvidenceUnavailable("GRAFANA_MCP_REQUIRED_TOOLS_MISSING")
        self._tools_verified = True

    async def _discover_datasources(self) -> None:
        if self._datasources:
            return
        payload = await self._call_tool("list_datasources", {"limit": 100})
        datasources = payload.get("datasources")
        if not isinstance(datasources, list):
            raise EvidenceUnavailable("GRAFANA_MCP_DATASOURCES_MALFORMED")
        for item in datasources:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("type", "")).lower()
            uid = item.get("uid")
            if uid and kind in {"prometheus", "loki"}:
                self._datasources[kind] = str(uid)
        if not {"prometheus", "loki"}.issubset(self._datasources):
            raise EvidenceUnavailable("GRAFANA_MCP_DATASOURCES_MISSING")

    @staticmethod
    def _timestamp(value: Any) -> datetime:
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise EvidenceUnavailable("GRAFANA_MCP_TIMESTAMP_MISSING") from exc
        if numeric > 1_000_000_000_000:
            numeric /= 1_000_000_000
        return datetime.fromtimestamp(numeric, tz=UTC)

    @classmethod
    def _metric_evidence(
        cls, payload: dict[str, Any], run_id: str, phase: str
    ) -> Evidence:
        data = payload.get("data")
        result = data.get("result") if isinstance(data, dict) else None
        if not isinstance(result, list) or not result:
            raise EvidenceUnavailable("GRAFANA_MCP_METRIC_EVIDENCE_MISSING")
        values: dict[str, Any] = {}
        observed: list[datetime] = []
        provider_runs: set[str] = set()
        for series in result:
            if not isinstance(series, dict):
                continue
            labels = series.get("metric", {})
            point = series.get("value")
            if (
                not isinstance(labels, dict)
                or not isinstance(point, list)
                or len(point) < 2
            ):
                continue
            name = str(labels.get("__name__", ""))
            provider_run = labels.get("run_id")
            if provider_run:
                provider_runs.add(str(provider_run))
            observed.append(cls._timestamp(point[0]))
            numeric = float(point[1])
            if name == "cutline_release_backlog_frames":
                values["backlog_frames"] = int(numeric)
            elif name == "cutline_render_throughput_fpm":
                values["throughput"] = int(numeric)
        if (
            provider_runs != {run_id}
            or "backlog_frames" not in values
            or "throughput" not in values
            or not observed
        ):
            raise EvidenceUnavailable("GRAFANA_MCP_METRIC_PROVENANCE_INVALID")
        return Evidence(
            id=f"{phase}-metric-{run_id[:8]}",
            kind="metric",
            operation="query_prometheus",
            summary=(
                f"Backlog {values['backlog_frames']}; throughput "
                f"{values['throughput']} frames/min"
            ),
            observed_at=max(observed),
            run_id=run_id,
            source_mode=EvidenceMode.LIVE,
            values=values,
        )

    @classmethod
    def _log_evidence(
        cls, payload: dict[str, Any], run_id: str, phase: str
    ) -> Evidence:
        data = payload.get("data")
        if not isinstance(data, list) or not data:
            raise EvidenceUnavailable("GRAFANA_MCP_LOG_EVIDENCE_MISSING")
        entry = data[0]
        if not isinstance(entry, dict):
            raise EvidenceUnavailable("GRAFANA_MCP_LOG_EVIDENCE_MALFORMED")
        labels = entry.get("labels", {})
        line = entry.get("line")
        if not isinstance(labels, dict) or labels.get("run_id") != run_id:
            raise EvidenceUnavailable("GRAFANA_MCP_LOG_PROVENANCE_INVALID")
        try:
            event = json.loads(line)
        except (TypeError, ValueError) as exc:
            raise EvidenceUnavailable("GRAFANA_MCP_LOG_EVIDENCE_MALFORMED") from exc
        if not isinstance(event, dict) or not isinstance(event.get("oom"), bool):
            raise EvidenceUnavailable("GRAFANA_MCP_LOG_EVIDENCE_MALFORMED")
        oom = event["oom"]
        return Evidence(
            id=f"{phase}-log-{run_id[:8]}",
            kind="log",
            operation="query_loki_logs",
            summary="CUDA OOM persists" if oom else "No new CUDA OOM events",
            observed_at=cls._timestamp(entry.get("timestamp")),
            run_id=run_id,
            source_mode=EvidenceMode.LIVE,
            values={"oom": oom, "event": event.get("event", "render_status")},
        )

    async def collect(self, run_id: str, after_action: bool) -> list[Evidence]:
        if not self.url:
            raise EvidenceUnavailable("LIVE_GRAFANA_MCP_NOT_CONFIGURED")
        phase = "post_action" if after_action else "pre_action"
        try:
            await self._verify_tools()
            await self._discover_datasources()
            metric_payload = await self._call_tool(
                "query_prometheus",
                {
                    "datasourceUid": self._datasources["prometheus"],
                    "expr": (
                        f'cutline_release_backlog_frames{{run_id="{run_id}"}} '
                        f'or cutline_render_throughput_fpm{{run_id="{run_id}"}}'
                    ),
                    "endTime": "now",
                    "queryType": "instant",
                },
            )
            log_payload = await self._call_tool(
                "query_loki_logs",
                {
                    "datasourceUid": self._datasources["loki"],
                    "logql": (f'{{service_name="cutline-workload",run_id="{run_id}"}}'),
                    "startRfc3339": "now-15m",
                    "endRfc3339": "now",
                    "limit": 1,
                    "direction": "backward",
                },
            )
            return [
                self._metric_evidence(metric_payload, run_id, phase),
                self._log_evidence(log_payload, run_id, phase),
            ]
        except (httpx.HTTPError, OSError, ValueError, TypeError) as exc:
            raise EvidenceUnavailable("GRAFANA_MCP_REQUEST_FAILED") from exc


class ActionExecutor(ABC):
    @abstractmethod
    async def execute(
        self, *, run_id: str, approval_id: str, idempotency_key: str
    ) -> dict[str, Any]:
        raise NotImplementedError


class LocalActionExecutor(ActionExecutor):
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    async def execute(
        self, *, run_id: str, approval_id: str, idempotency_key: str
    ) -> dict[str, Any]:
        if self.fail:
            raise ActionUnavailable("LOCAL_ACTION_FAILED")
        return {
            "executor_mode": "LOCAL_CONTROLLED",
            "transition": {
                "concurrency_before": 3,
                "concurrency_after": 1,
                "reserve_workers_before": 0,
                "reserve_workers_after": 4,
            },
            "annotation_id": f"annotation-{run_id[:8]}",
        }


class CloudRunActionExecutor(ActionExecutor):
    def __init__(self, url: str | None = None, token: str | None = None) -> None:
        self.url = url or os.getenv("CUTLINE_ACTION_URL")
        self.token = token or os.getenv("CUTLINE_ACTION_TOKEN")

    async def execute(
        self, *, run_id: str, approval_id: str, idempotency_key: str
    ) -> dict[str, Any]:
        if not self.url or not self.token:
            raise ActionUnavailable("CLOUD_RUN_ACTION_NOT_CONFIGURED")
        try:
            async with httpx.AsyncClient(
                timeout=20,
                headers={"Authorization": f"Bearer {self.token}"},
            ) as client:
                response = await client.post(
                    self.url,
                    json={
                        "run_id": run_id,
                        "approval_id": approval_id,
                        "idempotency_key": idempotency_key,
                        "plan_version": "sq42-recovery-v1",
                    },
                )
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ActionUnavailable("CLOUD_RUN_ACTION_FAILED") from exc
