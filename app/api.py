"""CUTLINE FastAPI product surface."""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.actions import (
    ActionBoundaryError,
    ActionRecordStore,
    action_store_from_environment,
    execute_recovery_action,
)
from app.adapters import (
    CloudRunActionExecutor,
    LiveGrafanaMCPAdapter,
    LiveGrafanaTelemetryPublisher,
    LocalActionExecutor,
    LocalGrafanaAdapter,
)
from app.agent_runtime import (
    ADKHostedInvestigator,
    AgentSynthesisUnavailable,
    HostedInvestigator,
)
from app.domain import EvidenceMode
from app.service import CutlineService, WorkflowError

WEB = Path(__file__).parent / "web"


class DecisionRequest(BaseModel):
    approver: str = Field(default="Maya Chen", min_length=1, max_length=80)
    reason: str | None = Field(default=None, max_length=240)


class ExecuteRequest(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=120)


class LiveActionRequest(BaseModel):
    run_id: str = Field(min_length=8, max_length=80)
    approval_id: str = Field(min_length=8, max_length=80)
    idempotency_key: str = Field(min_length=8, max_length=120)
    plan_version: Literal["sq42-recovery-v1"]


def service_from_environment() -> CutlineService:
    live = os.getenv("CUTLINE_MODE", "local").lower() == "live"
    if live:
        return CutlineService(
            LiveGrafanaMCPAdapter(),
            CloudRunActionExecutor(),
            LiveGrafanaTelemetryPublisher(),
        )
    return CutlineService(LocalGrafanaAdapter(), LocalActionExecutor())


def create_app(
    service: CutlineService | None = None,
    action_store: ActionRecordStore | None = None,
    investigator: HostedInvestigator | None = None,
) -> FastAPI:
    app = FastAPI(
        title="CUTLINE",
        description="Release assurance for agentic cinema",
        version="1.0.0",
    )
    app.state.cutline = service or service_from_environment()
    app.state.action_store = action_store or action_store_from_environment()
    app.state.investigator = investigator
    if (
        app.state.investigator is None
        and app.state.cutline.get().mode == EvidenceMode.LIVE
    ):
        app.state.investigator = ADKHostedInvestigator()
    app.mount("/assets", StaticFiles(directory=WEB), name="assets")

    @app.exception_handler(WorkflowError)
    async def workflow_error(_request: Request, exc: WorkflowError) -> JSONResponse:
        scenario = app.state.cutline.get()
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": str(exc),
                    "run_id": scenario.run_id,
                    "guidance": "Retry the step or reset the controlled scenario.",
                }
            },
        )

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(WEB / "index.html")

    @app.get("/health")
    @app.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/readiness")
    async def readiness() -> dict[str, object]:
        scenario = app.state.cutline.get()
        live = scenario.mode == EvidenceMode.LIVE
        configured = bool(
            os.getenv("GRAFANA_MCP_URL")
            and (
                os.getenv("GRAFANA_MCP_TOKEN")
                or os.getenv("GRAFANA_MCP_USE_GOOGLE_ID_TOKEN", "").lower() == "true"
            )
            and os.getenv("GRAFANA_PROMETHEUS_DATASOURCE_UID")
            and os.getenv("GRAFANA_LOKI_DATASOURCE_UID")
            and os.getenv("CUTLINE_ACTION_URL")
            and os.getenv("CUTLINE_ACTION_TOKEN")
            and os.getenv("GRAFANA_PROMETHEUS_PUSH_URL")
            and os.getenv("GRAFANA_PROMETHEUS_USER")
            and os.getenv("GRAFANA_LOKI_PUSH_URL")
            and os.getenv("GRAFANA_LOKI_USER")
            and os.getenv("GRAFANA_TELEMETRY_TOKEN")
        )
        blockers = list(scenario.blockers)
        if live and not configured:
            blockers.append("LIVE_RUNTIME_CONFIGURATION_INCOMPLETE")
        return {
            "ready": not blockers,
            "mode": scenario.mode,
            "run_id": scenario.run_id,
            "state": scenario.state,
            "blockers": blockers,
            "disclosure": scenario.disclosure,
        }

    @app.get("/api/scenario")
    async def get_scenario():
        return app.state.cutline.get()

    @app.post("/api/scenario/reset")
    async def reset():
        return app.state.cutline.reset()

    @app.post("/api/scenario/investigate")
    async def investigate():
        scenario = await app.state.cutline.investigate()
        if scenario.mode != EvidenceMode.LIVE:
            return scenario
        try:
            synthesis = await app.state.investigator.synthesize(scenario.run_id)
            return app.state.cutline.record_agent_synthesis(scenario.run_id, synthesis)
        except AgentSynthesisUnavailable as exc:
            app.state.cutline.block_agent_synthesis(scenario.run_id, str(exc))
            raise WorkflowError(
                "AGENT_SYNTHESIS_UNAVAILABLE",
                "Gemini synthesis is unavailable; no live recovery can be approved.",
                503,
            ) from exc

    @app.post("/api/scenario/approve")
    async def approve(request: DecisionRequest):
        return app.state.cutline.decide(
            approve=True, approver=request.approver, reason=request.reason
        )

    @app.post("/api/scenario/reject")
    async def reject(request: DecisionRequest):
        return app.state.cutline.decide(
            approve=False, approver=request.approver, reason=request.reason
        )

    @app.post("/api/scenario/execute")
    async def execute(request: ExecuteRequest):
        return await app.state.cutline.execute(request.idempotency_key)

    @app.post("/api/scenario/verify")
    async def verify():
        return await app.state.cutline.verify()

    @app.get("/api/audit")
    async def audit():
        return app.state.cutline.audit()

    @app.post("/internal/actions/sq42-recovery")
    async def live_action(request: Request, action: LiveActionRequest):
        expected = os.getenv("CUTLINE_ACTION_TOKEN")
        supplied = request.headers.get("authorization", "")
        if not expected:
            raise HTTPException(
                status_code=503, detail="ACTION_BOUNDARY_NOT_CONFIGURED"
            )
        if not secrets.compare_digest(supplied, f"Bearer {expected}"):
            raise HTTPException(status_code=401, detail="ACTION_BOUNDARY_UNAUTHORIZED")
        try:
            return await execute_recovery_action(
                app.state.action_store,
                run_id=action.run_id,
                approval_id=action.approval_id,
                idempotency_key=action.idempotency_key,
                plan_version=action.plan_version,
            )
        except ActionBoundaryError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return app


app = create_app()
