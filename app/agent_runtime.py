"""Hosted Google ADK runner used by the public live investigation path."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from google.adk.runners import InMemoryRunner
from google.genai import types


class AgentSynthesisUnavailable(RuntimeError):
    pass


class HostedInvestigator(ABC):
    @abstractmethod
    async def synthesize(self, run_id: str) -> str:
        raise NotImplementedError


class ADKHostedInvestigator(HostedInvestigator):
    def __init__(
        self,
        runner_factory: Callable[..., Any] = InMemoryRunner,
        agent_app: Any | None = None,
    ) -> None:
        self.runner_factory = runner_factory
        self.agent_app = agent_app

    async def synthesize(self, run_id: str) -> str:
        if self.agent_app is None:
            from app.agent import app as agent_app
        else:
            agent_app = self.agent_app
        runner = self.runner_factory(app=agent_app)
        try:
            await runner.session_service.create_session(
                app_name=agent_app.name,
                user_id="cutline-hosted",
                session_id=run_id,
            )
            message = types.Content(
                role="user",
                parts=[
                    types.Part(
                        text=(
                            "Inspect the active CUTLINE release state with the "
                            "get_release_state tool. Return a concise evidence-grounded "
                            "synthesis citing evidence IDs, separating observations from "
                            "the leading hypothesis, and retaining the strongest "
                            "alternative and falsifier. Do not calculate, approve, "
                            "execute, or verify."
                        )
                    )
                ],
            )
            final_text = ""
            async for event in runner.run_async(
                user_id="cutline-hosted",
                session_id=run_id,
                new_message=message,
            ):
                if not event.is_final_response() or not event.content:
                    continue
                final_text = "\n".join(
                    part.text
                    for part in event.content.parts
                    if getattr(part, "text", None)
                ).strip()
            if not final_text:
                raise AgentSynthesisUnavailable("ADK_AGENT_EMPTY_RESPONSE")
            return final_text
        except AgentSynthesisUnavailable:
            raise
        except Exception as exc:
            raise AgentSynthesisUnavailable("ADK_AGENT_REQUEST_FAILED") from exc
        finally:
            await runner.close()
