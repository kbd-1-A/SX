"""用户性格与说话偏好画像测试。"""

import pytest


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    import app.db.init as init_mod
    from app.memory import behavior as behavior_mod

    db = tmp_path / "test.db"
    monkeypatch.setattr(behavior_mod, "DB_PATH", db)
    monkeypatch.setattr(init_mod, "DB_PATH", db)
    init_mod.init_db()
    return db


def test_repeated_trait_only_activates_after_three_observations(tmp_db):
    from app.memory.behavior import get_behavior_profile, observe_behavior

    for message_id in range(1, 3):
        observe_behavior("这件事我想先确认风险，稳妥一些。", message_id)

    candidate = get_behavior_profile()["traits"]["cautious"]
    assert candidate["status"] == "candidate"
    assert candidate["observations"] == 2

    observe_behavior("保险起见，我们还是先验证一下。", 3)
    active = get_behavior_profile()["traits"]["cautious"]
    assert active["status"] == "active"
    assert active["confidence"] >= 0.75
    assert len(active["evidence"]) == 3


def test_explicit_style_conflict_replaces_old_preference(tmp_db):
    from app.memory.behavior import format_behavior_profile, get_behavior_profile, observe_behavior

    observe_behavior("以后回复短一点，别写太长。", 1)
    before = get_behavior_profile()["styles"]["short_reply"]
    assert before["status"] == "active"

    observe_behavior("以后请详细一点，展开说。", 2)
    styles = get_behavior_profile()["styles"]
    assert styles["short_reply"]["status"] == "stale"
    assert styles["detailed_reply"]["status"] == "active"

    prompt = format_behavior_profile()
    assert "偏好详细回复" in prompt
    assert "偏好简短回复" not in prompt


def test_inactive_profile_expires_and_is_not_injected(tmp_db, monkeypatch):
    import app.memory.behavior as behavior_mod
    from app.memory.behavior import format_behavior_profile, get_behavior_profile, observe_behavior

    for message_id in range(1, 4):
        observe_behavior("哈哈，这也太好笑了。", message_id)
    assert get_behavior_profile()["traits"]["humorous"]["status"] == "active"

    monkeypatch.setattr(behavior_mod, "PROFILE_EXPIRY_DAYS", -1)
    expired = get_behavior_profile()["traits"]["humorous"]
    assert expired["status"] == "stale"
    assert "幽默" not in format_behavior_profile()
