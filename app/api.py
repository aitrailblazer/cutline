"""CUTLINE FastAPI product surface."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.adapters import (
    CloudRunActionExecutor,
    LiveGrafanaMCPAdapter,
    LocalActionExecutor,
    LocalGrafanaAdapter,
)
from app.domain import EvidenceMode
from app.service import CutlineService, WorkflowError

WEB = Path(__file__).parent / "web"


class DecisionRequest(BaseModel):
    approver: str = Field(default="Maya Chen", min_length=1, max_length=80)
    reason: str | None = Field(default=None, max_length=240)


class ExecuteRequest(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=120)


def service_from_environment() -> CutlineService:
    live = os.getenv("CUTLINE_MODE", "local").lower() == "live"
    if live:
        return CutlineService(LiveGrafanaMCPAdapter(), CloudRunActionExecutor())
    return CutlineService(LocalGrafanaAdapter(), LocalActionExecutor())


def create_app(service: CutlineService | None = None) -> FastAPI:
    app = FastAPI(
        title="CUTLINE",
        description="Release assurance for agentic cinema",
        version="1.0.0",
    )
    app.state.cutline = service or service_from_environment()
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
            and os.getenv("GRAFANA_MCP_TOKEN")
            and os.getenv("CUTLINE_ACTION_URL")
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
        return await app.state.cutline.investigate()

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

    return app


app = create_app()
