"""固定对话基线：路由、对话动作与人工评测要点的稳定契约。"""

import json
from pathlib import Path

import pytest

from app.agents.mask import DEFAULT_MASK, detect_mask_by_keywords
from app.agents.reply_mode import detect_reply_mode

BASELINE_PATH = Path(__file__).parent / "fixtures" / "dialogue_baseline.json"
BASELINE_CASES = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def test_baseline_has_expected_coverage():
    assert 30 <= len(BASELINE_CASES) <= 50
    assert len({case["id"] for case in BASELINE_CASES}) == len(BASELINE_CASES)
    assert {case["category"] for case in BASELINE_CASES} >= {
        "daily",
        "love",
        "vent",
        "work",
        "ambiguous",
        "boundary",
    }
    for case in BASELINE_CASES:
        assert case["user_message"].strip()
        assert case["expected_reply_mode"].strip()
        assert case["checks"]


@pytest.mark.parametrize("case", BASELINE_CASES, ids=lambda case: case["id"])
def test_dialogue_baseline_routes_are_stable(case):
    detected_mask = detect_mask_by_keywords(case["user_message"])
    assert detected_mask == case["expected_mask"]

    routing_mask = detected_mask or DEFAULT_MASK
    assert (
        detect_reply_mode(case["user_message"], mask=routing_mask)
        == case["expected_reply_mode"]
    )
