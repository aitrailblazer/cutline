import pytest

from app.domain import calculate_impact, seed_shots


def test_deadline_math_before_and_after():
    before = calculate_impact(4800, 24, 120)
    assert before.model_dump(exclude={"formulas"}) == {
        "backlog_frames": 4800,
        "deadline_minutes": 24,
        "observed_throughput": 120,
        "deadline_minimum": 200,
        "safe_target": 240,
        "projected_minutes": 40,
        "variance_minutes": -16,
        "label": "16 minutes late",
    }
    assert before.formulas == [
        "4800 / 24 = 200 deadline minimum",
        "200 * 1.20 = 240 safe target",
        "4800 / 120 = 40 projected minutes",
        "24 - 40 = -16 deadline variance",
    ]
    after = calculate_impact(4800, 24, 320)
    assert (after.projected_minutes, after.variance_minutes, after.label) == (
        15,
        9,
        "9 minutes early",
    )


@pytest.mark.parametrize("values", [(0, 24, 120), (4800, 0, 120), (4800, 24, 0)])
def test_deadline_math_rejects_nonpositive_inputs(values):
    with pytest.raises(ValueError, match="must be positive"):
        calculate_impact(*values)


def test_seed_manifest_is_media_native():
    shots = seed_shots()
    assert len(shots) == 18
    assert len({shot.id for shot in shots}) == 18
    assert sum(shot.at_risk for shot in shots) == 12
    assert shots[0].model_dump() == {
        "id": "SQ42-001",
        "frame_start": 1,
        "frame_end": 300,
        "remaining_frames": 400,
        "attempts": 3,
        "worker": "gpu-01",
        "eta_minutes": 28,
        "dependency": "Streaming package",
        "at_risk": True,
        "status": "AT RISK",
    }
    recovered = seed_shots(0)
    assert not any(shot.at_risk for shot in recovered)
    assert all(shot.status == "READY" for shot in recovered)
