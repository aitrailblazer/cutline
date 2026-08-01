from types import SimpleNamespace
from typing import ClassVar

import pytest
from google.genai import types

from app.agent_runtime import ADKHostedInvestigator, AgentSynthesisUnavailable


class FakeEvent:
    def __init__(self, text=None, final=True):
        self.content = (
            types.Content(role="model", parts=[types.Part(text=text)])
            if text is not None
            else None
        )
        self.final = final

    def is_final_response(self):
        return self.final


class FakeSessionService:
    async def create_session(self, **_kwargs):
        return None


class FakeRunner:
    events: ClassVar[list[FakeEvent]] = []
    run_error = None

    def __init__(self, app):
        self.app = app
        self.session_service = FakeSessionService()
        self.closed = False

    async def run_async(self, **_kwargs):
        if self.run_error:
            raise self.run_error
        for event in self.events:
            yield event

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_adk_hosted_investigator_extracts_final_text():
    FakeRunner.run_error = None
    FakeRunner.events = [
        FakeEvent("tool activity", final=False),
        FakeEvent("Evidence pre-1 supports the hypothesis."),
    ]
    investigator = ADKHostedInvestigator(
        runner_factory=FakeRunner,
        agent_app=SimpleNamespace(name="app"),
    )
    assert (
        await investigator.synthesize("run-12345678")
        == "Evidence pre-1 supports the hypothesis."
    )
    default_app_investigator = ADKHostedInvestigator(runner_factory=FakeRunner)
    assert "pre-1" in await default_app_investigator.synthesize("run-default-app")


@pytest.mark.asyncio
async def test_adk_hosted_investigator_fails_closed():
    investigator = ADKHostedInvestigator(
        runner_factory=FakeRunner,
        agent_app=SimpleNamespace(name="app"),
    )
    FakeRunner.run_error = None
    FakeRunner.events = [FakeEvent()]
    with pytest.raises(AgentSynthesisUnavailable, match="EMPTY_RESPONSE"):
        await investigator.synthesize("run-12345678")
    FakeRunner.run_error = RuntimeError("provider down")
    with pytest.raises(AgentSynthesisUnavailable, match="REQUEST_FAILED"):
        await investigator.synthesize("run-12345678")
    FakeRunner.run_error = None
