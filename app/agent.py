"""Google ADK evidence-synthesis agent for CUTLINE."""

from __future__ import annotations

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

from app.api import app as api_app


async def get_release_state() -> dict:
    """Return the current deterministic CUTLINE scenario."""
    return api_app.state.cutline.get().model_dump(mode="json")


async def investigate_release_risk() -> dict:
    """Retrieve evidence and create the bounded diagnosis and proposal."""
    return (await api_app.state.cutline.investigate()).model_dump(mode="json")


root_agent = Agent(
    name="cutline_release_assurance",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are CUTLINE's bounded evidence-synthesis agent. Use tool evidence, "
        "cite evidence IDs, distinguish observed facts from hypotheses, preserve "
        "the strongest alternative and falsifier, and never invent telemetry. "
        "Never perform authoritative deadline arithmetic, execute recovery, "
        "bypass approval, or declare success; deterministic services own those."
    ),
    tools=[get_release_state, investigate_release_risk],
)

app = App(root_agent=root_agent, name="app")
