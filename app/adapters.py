"""Evidence and action adapters with explicit local/live boundaries."""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from datetime import timedelta
from typing import Any

import httpx
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

    async def _call_tool(  # pragma: no cover - exercised only against a live MCP server
        self, name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        async with httpx.AsyncClient(headers=headers, timeout=20) as client:
            async with streamable_http_client(self.url, http_client=client) as streams:
                read_stream, write_stream, _ = streams
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool(name, arguments)
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

    async def collect(self, run_id: str, after_action: bool) -> list[Evidence]:
        if not self.url:
            raise EvidenceUnavailable("LIVE_GRAFANA_MCP_NOT_CONFIGURED")
        phase = "post_action" if after_action else "pre_action"
        calls = [
            ("alert", "get_alert_rule_by_uid", {"uid": "cutline-render-deadline"}),
            (
                "metric",
                "query_prometheus",
                {
                    "expr": (
                        'cutline_release_backlog_frames{sequence="SQ-42"} '
                        'or cutline_render_throughput_fpm{sequence="SQ-42"}'
                    ),
                },
            ),
            (
                "log",
                "query_loki_logs",
                {"query": '{sequence="SQ-42"} |= "CUDA OOM"'},
            ),
            ("trace", "get_trace", {"trace_id": f"{run_id}-{phase}"}),
        ]
        evidence: list[Evidence] = []
        try:
            for index, (kind, operation, arguments) in enumerate(calls, 1):
                payload = await self._call_tool(operation, arguments)
                evidence.append(
                    Evidence(
                        id=str(payload.get("id", f"{phase}-{index}-{run_id[:8]}")),
                        kind=kind,
                        operation=operation,
                        summary=str(payload.get("summary", operation)),
                        observed_at=payload.get("observed_at", utcnow()),
                        run_id=str(payload.get("run_id", run_id)),
                        source_mode=self.mode,
                        values=dict(payload.get("values", payload)),
                    )
                )
        except (httpx.HTTPError, OSError, ValueError, TypeError) as exc:
            raise EvidenceUnavailable("GRAFANA_MCP_REQUEST_FAILED") from exc
        return evidence


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
    def __init__(self, url: str | None = None) -> None:
        self.url = url or os.getenv("CUTLINE_ACTION_URL")

    async def execute(
        self, *, run_id: str, approval_id: str, idempotency_key: str
    ) -> dict[str, Any]:
        if not self.url:
            raise ActionUnavailable("CLOUD_RUN_ACTION_NOT_CONFIGURED")
        try:
            async with httpx.AsyncClient(timeout=20) as client:
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
