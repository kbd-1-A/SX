from app.agents.emotion import (
    adjust_reply_mode,
    detect_emotion_state,
    format_emotion_strategy,
)


def test_detects_tired_state_and_reduce_load_strategy():
    state = detect_emotion_state("今天好累，真的没力气")

    assert state["emotion"] == "tired"
    assert state["user_need"] == "rest"
    assert state["strategy"] == "reduce_load"
    assert state["strategy_scores"]["reduce_load"] > state["strategy_scores"]["catch_up"]


def test_distinguishes_need_for_solution_from_need_to_be_heard():
    state = detect_emotion_state("我很焦虑，你觉得我该怎么办")

    assert state["emotion"] == "anxious"
    assert state["user_need"] == "solve_problem"
    assert state["strategy"] == "action_advice"


def test_sensitive_self_harm_scene_uses_safety_support():
    state = detect_emotion_state("我不想活了，感觉撑不住")

    assert state["emotion"] == "crisis"
    assert state["sensitive_scene"] == "self_harm"
    assert state["risk_level"] == "high"
    assert state["strategy"] == "safety_support"
    assert adjust_reply_mode("catch_up", state) == "comfort"
    assert "现实中可信的人" in format_emotion_strategy(state)


def test_angry_state_keeps_venting_from_turning_into_lecture():
    state = detect_emotion_state("这破事太离谱了，我真的服了")

    assert state["emotion"] == "angry"
    assert state["strategy"] == "validate_vent"
    assert adjust_reply_mode("catch_up", state) == "vent_with_user"