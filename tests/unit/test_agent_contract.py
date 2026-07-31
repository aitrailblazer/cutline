import json
from pathlib import Path

import pytest

from app.agent import get_release_state, investigate_release_risk, root_agent


@pytest.mark.asyncio
async def test_adk_agent_is_bounded_and_uses_cutline_tools():
    state = await get_release_state()
    assert state["state"] == "READY"
    investigated = await investigate_release_risk()
    assert investigated["state"] == "AWAITING_APPROVAL"
    assert root_agent.name == "cutline_release_assurance"
    instruction = root_agent.instruction.lower()
    assert "never invent telemetry" in instruction
    assert "never perform authoritative deadline arithmetic" in instruction
    assert "uses tool evidence" in instruction
    assert "without asking a follow-up question" in instruction
    assert root_agent.model.model == "gemini-2.5-flash"
    assert root_agent.generate_content_config.temperature == 0
    assert len(root_agent.tools) == 2


def test_eval_dataset_targets_capability_investigation_and_safety():
    path = Path("tests/eval/datasets/basic-dataset.json")
    cases = json.loads(path.read_text())["eval_cases"]
    assert [case["eval_case_id"] for case in cases] == [
        "cutline_capability_boundary",
        "cutline_investigation",
        "cutline_refuses_unauthorized_execution",
    ]
